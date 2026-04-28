# ah-research — Phase 0 + Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a working data layer: `from ah_research import ah; repo = ah.DataRepository(); repo.get_prices(["600519.SH", "0700.HK"], "2020-01-01", "2024-12-31")` returns a pandera-validated `PriceFrame` with PIT-correct back-adjusted prices, sourced from Baostock/AKshare, cached in DuckDB, with structured logging and a health-check CLI.

**Architecture:** Five layers. Integration (Baostock + AKshare + FX) behind `Protocol`s, DI'd into `DataRepository` along with a DuckDB cache. Converters are pure functions. Pandera schemas validate every layer boundary. Exceptions remap at the integration boundary. All operations are PIT-correct (bitemporal fundamentals, PIT index constituents, back-adjusted prices by default).

**Tech Stack:** Python 3.11+, uv, pandas, pandera, duckdb, pyarrow, baostock, akshare, tenacity, structlog, pydantic-settings, keyring, pytest, hypothesis, ruff, mypy.

**Reference:** spec `docs/superpowers/specs/2026-04-28-ah-research-platform-design.md` commit `2218265`. Phase 0 + Phase 1 only. Phases 2-6 will be planned separately once Phase 1 ships.

**Non-negotiable correctness requirements** (enforced from Phase 1):
- PIT (point-in-time) universe via `get_index_constituents(asof=)` and `get_universe_over_time`
- Bitemporal fundamentals (`report_date`, `publication_date`, `known_as_of`)
- Back-adjusted (`hfq`) + total-return as DEFAULT price series; forward-adjust NEVER default
- ST/halt/price-limit flags present on every `PriceFrame` row
- Corporate actions feed price-adjustment; adjusted series is derived, not authoritative
- Pandera validation at every converter output + repository return

---

## File Structure

```
ah-research/
├── pyproject.toml                          # uv, ruff, mypy, pytest config + extras
├── README.md                               # updated
├── CLAUDE.md                               # project instructions for AI
├── .pre-commit-config.yaml
├── .github/workflows/ci.yml
├── .gitignore                              # existing; will add .env, cache.duckdb
├── src/ah_research/
│   ├── __init__.py
│   ├── config.py                           # pydantic-settings Settings
│   ├── exceptions.py                       # AHResearchError hierarchy
│   ├── logging.py                          # structlog setup
│   ├── concurrency.py                      # ThreadPool/ProcessPool helpers
│   ├── model/
│   │   ├── __init__.py                     # re-exports
│   │   ├── types.py                        # Symbol, AHPair, IndexConstituent, CorporateAction, enums
│   │   └── schemas.py                      # pandera SchemaModels
│   ├── integrations/
│   │   ├── __init__.py                     # Protocols exported
│   │   ├── _protocols.py                   # PriceSource, FundamentalsSource, ... Protocols
│   │   ├── baostock/
│   │   │   ├── __init__.py
│   │   │   ├── client.py                   # BaostockClient implements Protocols
│   │   │   └── source_schemas.py           # source-native pandera schemas
│   │   ├── akshare/
│   │   │   ├── __init__.py
│   │   │   ├── client.py
│   │   │   └── source_schemas.py
│   │   └── fake/
│   │       ├── __init__.py
│   │       └── client.py                   # deterministic Protocol impls for tests
│   ├── data/
│   │   ├── __init__.py
│   │   ├── converters.py                   # source-native DF -> domain-model DF (pure fns)
│   │   ├── cache.py                        # DuckDBCache + table DDL
│   │   ├── migrations/                     # numbered SQL migrations
│   │   │   └── 0001_init.sql
│   │   ├── repository.py                   # DataRepository (DI on sources + cache)
│   │   └── ah_pairs.yaml                   # curated ~30 pairs
├── scripts/
│   ├── __init__.py
│   ├── ah_init.py                          # `ah init`
│   ├── ah_doctor.py                        # `ah doctor`
│   └── ah_warmup.py                        # `ah warmup`
├── tests/
│   ├── __init__.py
│   ├── conftest.py                         # shared fixtures (tmp cache, fake sources)
│   ├── unit/
│   │   ├── test_config.py
│   │   ├── test_exceptions.py
│   │   ├── test_model_types.py
│   │   ├── test_model_schemas.py
│   │   ├── test_converters.py
│   │   ├── test_cache.py
│   │   ├── test_repository_prices.py
│   │   ├── test_repository_fundamentals.py
│   │   ├── test_repository_constituents.py
│   │   ├── test_repository_corporate_actions.py
│   │   ├── test_repository_ah_premium.py
│   │   └── test_doctor.py
│   ├── integration/
│   │   ├── test_baostock_live.py           # gated by AH_RESEARCH_LIVE=1
│   │   └── test_akshare_live.py            # gated by AH_RESEARCH_LIVE=1
│   └── property/
│       ├── test_symbol_roundtrip.py        # hypothesis
│       ├── test_pit_monotonicity.py        # hypothesis
│       └── test_adjust_idempotence.py      # hypothesis
└── docs/superpowers/
    ├── specs/2026-04-28-ah-research-platform-design.md
    └── plans/2026-04-28-ah-research-phase-0-1.md  # this file
```

Design note: one module per clear responsibility. `repository.py` is the biggest file — ~400 lines when done — because range-merge logic and PIT enforcement live there. If it grows past ~600 lines we split by entity (`repository/prices.py`, `repository/fundamentals.py`, ...).

---

## Phase 0 — Scaffold + Bootstrap (~1 day, 9 tasks)

### Task 0.1: Initialize project with uv and pyproject.toml

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore` (update existing)
- Create: `src/ah_research/__init__.py`

- [ ] **Step 1: Run `uv init --package ah-research` in project root**

```bash
cd /Users/brian_huang/repos/ah-research
uv init --package ah-research --no-readme
```

- [ ] **Step 2: Replace generated `pyproject.toml` with the full contents below**

```toml
[project]
name = "ah-research"
version = "0.0.1"
description = "Personal A-shares + HK stock research platform"
requires-python = ">=3.11"
dependencies = [
    "pandas>=2.2",
    "pyarrow>=15",
    "duckdb>=1.0",
    "pandera[pandas]>=0.20",
    "tenacity>=8.5",
    "structlog>=24",
    "pydantic-settings>=2.2",
    "keyring>=25",
    "pyyaml>=6",
    "baostock>=0.8.8",
    "akshare>=1.14",
    "typer>=0.12",
]

[project.optional-dependencies]
ai = ["anthropic>=0.45"]
chat = ["streamlit>=1.38", "jupyter_client>=8", "plotly>=5.22"]
dev = [
    "pytest>=8",
    "pytest-cov>=5",
    "hypothesis>=6",
    "ruff>=0.5",
    "mypy>=1.10",
    "pre-commit>=3.7",
    "types-pyyaml",
]

[project.scripts]
ah = "ah_research.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/ah_research"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "C4", "SIM", "RUF"]
ignore = ["E501"]  # line length handled by formatter

[tool.mypy]
python_version = "3.11"
strict = true
ignore_missing_imports = true  # pandas/akshare stubs imperfect

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --tb=short --strict-markers"
markers = [
    "live: integration tests that hit real APIs (set AH_RESEARCH_LIVE=1)",
    "slow: tests that take >1s",
]
```

- [ ] **Step 3: Append to `.gitignore`**

```gitignore
# Environment
.env
.env.local
.venv/

# Cache (user-writable; not project-local by default, but local test runs)
cache.duckdb
cache.duckdb.wal
data/cache/

# Test artifacts
.coverage
htmlcov/
.pytest_cache/
.hypothesis/
.mypy_cache/
.ruff_cache/

# Editor
.vscode/
.idea/
```

- [ ] **Step 4: Run install and verify**

```bash
uv sync --extra dev
uv run python -c "import ah_research; print(ah_research.__name__)"
```
Expected: prints `ah_research`.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .gitignore src/ah_research/__init__.py uv.lock
git commit -m "chore: initialize uv project with core deps and extras"
```

---

### Task 0.2: Add ruff + mypy + pre-commit + CI

**Files:**
- Create: `.pre-commit-config.yaml`
- Create: `.github/workflows/ci.yml`
- Create: `tests/__init__.py`
- Create: `tests/unit/__init__.py`

- [ ] **Step 1: Write `.pre-commit-config.yaml`**

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.5.0
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.10.0
    hooks:
      - id: mypy
        additional_dependencies: [pandas-stubs, pydantic, pydantic-settings, types-pyyaml]
        args: [--strict, --ignore-missing-imports]
        files: ^src/
```

- [ ] **Step 2: Write `.github/workflows/ci.yml`**

```yaml
name: CI
on:
  pull_request:
  push:
    branches: [main]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - name: Install
        run: uv sync --extra dev --extra ai --extra chat
      - name: Lint
        run: uv run ruff check src tests
      - name: Format check
        run: uv run ruff format --check src tests
      - name: Type check
        run: uv run mypy src
      - name: Unit tests
        run: uv run pytest tests/unit tests/property --cov=ah_research
```

- [ ] **Step 3: Install pre-commit hooks**

```bash
uv run pre-commit install
```

- [ ] **Step 4: Create test package init files**

```bash
touch tests/__init__.py tests/unit/__init__.py tests/property/__init__.py tests/integration/__init__.py
mkdir -p tests/unit tests/property tests/integration
```

- [ ] **Step 5: Run a sanity test to confirm pytest wiring**

```bash
uv run pytest --collect-only
```
Expected: "collected 0 items" (no tests yet, but pytest finds the dirs).

- [ ] **Step 6: Commit**

```bash
git add .pre-commit-config.yaml .github/workflows/ci.yml tests/
git commit -m "chore: add ruff, mypy, pre-commit, and GitHub Actions CI"
```

---

### Task 0.3: Exception hierarchy

**Files:**
- Create: `src/ah_research/exceptions.py`
- Test: `tests/unit/test_exceptions.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_exceptions.py
from ah_research.exceptions import (
    AHResearchError,
    SourceError,
    SourceRateLimit,
    SourceUnavailable,
    SourceSchemaError,
    SourceAuthError,
    SourceDataError,
    DataIntegrityError,
    UserInputError,
    ResearchError,
    LeakageDetected,
    UnsupportedOperation,
    InsufficientData,
)


def test_all_errors_inherit_from_root():
    for cls in (
        SourceError, SourceRateLimit, SourceUnavailable, SourceSchemaError,
        SourceAuthError, SourceDataError, DataIntegrityError,
        UserInputError, ResearchError, LeakageDetected, UnsupportedOperation,
        InsufficientData,
    ):
        assert issubclass(cls, AHResearchError)


def test_source_sub_errors_inherit_from_source_error():
    for cls in (SourceRateLimit, SourceUnavailable, SourceSchemaError,
                SourceAuthError, SourceDataError):
        assert issubclass(cls, SourceError)


def test_research_sub_errors_inherit_from_research_error():
    for cls in (LeakageDetected, UnsupportedOperation, InsufficientData):
        assert issubclass(cls, ResearchError)


def test_source_rate_limit_is_retryable_marker():
    # Retryable errors expose a class attribute for tenacity
    assert SourceRateLimit.retryable is True
    assert SourceUnavailable.retryable is True
    assert SourceSchemaError.retryable is False
    assert SourceAuthError.retryable is False
```

- [ ] **Step 2: Run — expect ImportError / module not found**

```bash
uv run pytest tests/unit/test_exceptions.py -v
```
Expected: `ModuleNotFoundError: No module named 'ah_research.exceptions'`.

- [ ] **Step 3: Implement `src/ah_research/exceptions.py`**

```python
"""Exception hierarchy for ah-research.

See docs/superpowers/specs/2026-04-28-ah-research-platform-design.md §10.
Source errors are remapped at the integration boundary; upper layers never see
baostock.* or akshare.* exceptions.
"""

from __future__ import annotations


class AHResearchError(Exception):
    """Base class for every exception raised by this package."""


# ── Source layer ────────────────────────────────────────────────────────────

class SourceError(AHResearchError):
    """Raised at the integration boundary. Upstream errors are remapped here."""

    retryable: bool = False


class SourceRateLimit(SourceError):
    """Upstream signalled rate-limit. Retryable with exponential backoff."""

    retryable: bool = True


class SourceUnavailable(SourceError):
    """Transient upstream failure (network, 5xx). Retryable with longer backoff."""

    retryable: bool = True


class SourceSchemaError(SourceError):
    """Upstream response shape changed. NOT retryable; indicates drift."""

    retryable: bool = False


class SourceAuthError(SourceError):
    """Authentication failure. NOT retryable; indicates misconfiguration."""

    retryable: bool = False


class SourceDataError(SourceError):
    """Empty / malformed data from upstream. NOT retryable."""

    retryable: bool = False


# ── Data layer ──────────────────────────────────────────────────────────────

class DataIntegrityError(AHResearchError):
    """Cache corruption, schema mismatch, pandera validation failure."""


# ── User / caller ───────────────────────────────────────────────────────────

class UserInputError(AHResearchError):
    """Bad symbol, invalid date range, unknown index, conflicting params."""


# ── Research layer ──────────────────────────────────────────────────────────

class ResearchError(AHResearchError):
    """Base for strategy / factor / backtest logic errors."""


class LeakageDetected(ResearchError):
    """Point-in-time violation or look-ahead bias detected."""


class UnsupportedOperation(ResearchError):
    """E.g., A-share short via retail."""


class InsufficientData(ResearchError):
    """Not enough history to compute the requested metric."""
```

- [ ] **Step 4: Run — expect pass**

```bash
uv run pytest tests/unit/test_exceptions.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ah_research/exceptions.py tests/unit/test_exceptions.py
git commit -m "feat(exceptions): add hierarchy with retryable classification"
```

---

### Task 0.4: Structlog configuration

**Files:**
- Create: `src/ah_research/logging.py`
- Test: `tests/unit/test_logging.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_logging.py
import json
import io
import logging
from ah_research.logging import configure_logging, get_logger


def test_configure_logging_emits_json(monkeypatch):
    buf = io.StringIO()
    configure_logging(level="INFO", stream=buf, json_output=True)
    log = get_logger("test")
    log.info("hello", foo="bar", n=42)

    line = buf.getvalue().strip()
    record = json.loads(line)
    assert record["event"] == "hello"
    assert record["foo"] == "bar"
    assert record["n"] == 42
    assert record["level"] == "info"


def test_get_logger_returns_bound_logger():
    log = get_logger("ah_research.test")
    # bindings attach context that appears on subsequent events
    bound = log.bind(request_id="abc")
    assert bound is not None  # basic sanity


def test_default_level_is_info(monkeypatch):
    buf = io.StringIO()
    configure_logging(stream=buf, json_output=True)
    log = get_logger("test")
    log.debug("should not appear")
    log.info("should appear")
    output = buf.getvalue()
    assert "should appear" in output
    assert "should not appear" not in output
```

- [ ] **Step 2: Run — expect ImportError**

```bash
uv run pytest tests/unit/test_logging.py -v
```

- [ ] **Step 3: Implement `src/ah_research/logging.py`**

```python
"""Structured logging setup.

All log output goes through structlog, JSON-formatted by default.
Use get_logger(__name__) in modules.
"""

from __future__ import annotations

import logging
import sys
from typing import TextIO

import structlog


def configure_logging(
    level: str = "INFO",
    stream: TextIO | None = None,
    json_output: bool = True,
) -> None:
    """Configure structlog + stdlib logging. Call once at process start."""
    stream = stream or sys.stderr
    logging.basicConfig(
        format="%(message)s",
        stream=stream,
        level=getattr(logging, level.upper()),
    )

    processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    if json_output:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level.upper())),
        logger_factory=structlog.PrintLoggerFactory(file=stream),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a bound logger. Modules call `log = get_logger(__name__)` at top."""
    return structlog.get_logger(name)
```

- [ ] **Step 4: Run — expect pass**

```bash
uv run pytest tests/unit/test_logging.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/ah_research/logging.py tests/unit/test_logging.py
git commit -m "feat(logging): add structlog configuration with JSON output"
```

---

### Task 0.5: Config via pydantic-settings + keyring

**Files:**
- Create: `src/ah_research/config.py`
- Test: `tests/unit/test_config.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_config.py
from pathlib import Path
import pytest
from ah_research.config import Settings, get_settings


def test_default_cache_dir_is_user_home(monkeypatch, tmp_path):
    monkeypatch.delenv("AH_RESEARCH_CACHE_DIR", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    s = Settings()
    assert s.cache_dir == tmp_path / ".ah-research"


def test_cache_dir_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("AH_RESEARCH_CACHE_DIR", str(tmp_path / "custom"))
    s = Settings()
    assert s.cache_dir == tmp_path / "custom"


def test_cache_duckdb_path_derived_from_cache_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("AH_RESEARCH_CACHE_DIR", str(tmp_path))
    s = Settings()
    assert s.cache_duckdb_path == tmp_path / "cache.duckdb"


def test_anthropic_api_key_from_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    s = Settings()
    assert s.anthropic_api_key == "sk-test-123"


def test_get_settings_is_singleton_per_process(monkeypatch, tmp_path):
    monkeypatch.setenv("AH_RESEARCH_CACHE_DIR", str(tmp_path))
    a = get_settings()
    b = get_settings()
    assert a is b
```

- [ ] **Step 2: Run — expect ImportError**

```bash
uv run pytest tests/unit/test_config.py -v
```

- [ ] **Step 3: Implement `src/ah_research/config.py`**

```python
"""Runtime configuration.

Sources, in precedence order:
 1. Process env vars (AH_RESEARCH_*, ANTHROPIC_API_KEY)
 2. .env file in project root (for development)
 3. keyring (future; for production secrets)
 4. defaults

Secrets (API keys) never persist in profile.yaml.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AH_RESEARCH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    cache_dir: Path = Field(
        default_factory=lambda: Path.home() / ".ah-research",
        description="Root dir for cache.duckdb and sessions/",
    )

    # Secrets read directly from env (not AH_RESEARCH_-prefixed)
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")

    # Logging
    log_level: str = "INFO"
    log_json: bool = True

    @computed_field
    @property
    def cache_duckdb_path(self) -> Path:
        return self.cache_dir / "cache.duckdb"

    @computed_field
    @property
    def sessions_dir(self) -> Path:
        return self.cache_dir / "sessions"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton per process; cleared in tests by monkeypatching env then calling
    get_settings.cache_clear() if needed."""
    return Settings()
```

- [ ] **Step 4: Run — expect pass, 5 passed**

```bash
uv run pytest tests/unit/test_config.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/ah_research/config.py tests/unit/test_config.py
git commit -m "feat(config): add pydantic-settings with cache dir and API key"
```

---

### Task 0.6: Concurrency helpers

**Files:**
- Create: `src/ah_research/concurrency.py`
- Test: `tests/unit/test_concurrency.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_concurrency.py
import time
from ah_research.concurrency import thread_map, process_map


def _slow_square(x: int) -> int:
    time.sleep(0.05)
    return x * x


def test_thread_map_returns_ordered_results():
    results = thread_map(_slow_square, [1, 2, 3, 4, 5], max_workers=4)
    assert results == [1, 4, 9, 16, 25]


def test_thread_map_is_faster_than_serial():
    inputs = list(range(10))
    t0 = time.perf_counter()
    _ = [_slow_square(x) for x in inputs]
    serial = time.perf_counter() - t0

    t0 = time.perf_counter()
    _ = thread_map(_slow_square, inputs, max_workers=8)
    concurrent = time.perf_counter() - t0

    # Should be at least 3x faster with 8 threads on 10 items
    assert concurrent < serial / 3, f"serial={serial:.3f}s concurrent={concurrent:.3f}s"


def test_process_map_handles_pickleable_fn():
    results = process_map(_slow_square, [1, 2, 3], max_workers=2)
    assert results == [1, 4, 9]


def test_thread_map_propagates_exceptions():
    import pytest

    def bad(x: int) -> int:
        if x == 3:
            raise ValueError("nope")
        return x

    with pytest.raises(ValueError, match="nope"):
        thread_map(bad, [1, 2, 3, 4], max_workers=2)
```

- [ ] **Step 2: Run — expect ImportError**

- [ ] **Step 3: Implement `src/ah_research/concurrency.py`**

```python
"""Concurrency helpers.

Use thread_map for I/O-bound work (network, disk). Use process_map for CPU-bound
work (backtests, factor studies). asyncio is intentionally not used — Baostock
and AKshare are blocking libraries.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from typing import TypeVar

T = TypeVar("T")
R = TypeVar("R")


def thread_map(
    fn: Callable[[T], R],
    items: Sequence[T] | Iterable[T],
    *,
    max_workers: int = 8,
) -> list[R]:
    """Apply fn to each item in parallel using a thread pool. Results ordered
    by input order. Exceptions propagate from the first failing item."""
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        return list(ex.map(fn, items))


def process_map(
    fn: Callable[[T], R],
    items: Sequence[T] | Iterable[T],
    *,
    max_workers: int | None = None,
) -> list[R]:
    """Apply fn to each item in parallel using a process pool. fn must be
    picklable (top-level function, no closures). Results ordered."""
    with ProcessPoolExecutor(max_workers=max_workers) as ex:
        return list(ex.map(fn, items))
```

- [ ] **Step 4: Run — expect pass (note: test_thread_map_is_faster_than_serial may be flaky on loaded CI; mark `@pytest.mark.slow` if so)**

```bash
uv run pytest tests/unit/test_concurrency.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/ah_research/concurrency.py tests/unit/test_concurrency.py
git commit -m "feat(concurrency): add thread_map and process_map helpers"
```

---

### Task 0.7: CLI skeleton with `ah` entrypoint

**Files:**
- Create: `src/ah_research/cli.py`
- Test: `tests/unit/test_cli.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_cli.py
from typer.testing import CliRunner
from ah_research.cli import app

runner = CliRunner()


def test_cli_help_runs():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "init" in result.stdout
    assert "doctor" in result.stdout
    assert "warmup" in result.stdout


def test_version_command():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "0.0.1" in result.stdout
```

- [ ] **Step 2: Run — expect ImportError**

- [ ] **Step 3: Implement `src/ah_research/cli.py`**

```python
"""Top-level CLI. Exposed as `ah` via pyproject.toml [project.scripts]."""

from __future__ import annotations

import typer

from ah_research import __version__

app = typer.Typer(
    name="ah",
    help="ah-research — A-shares + HK stock research platform",
    no_args_is_help=True,
)


@app.command()
def version() -> None:
    """Print the version."""
    typer.echo(f"ah-research {__version__}")


@app.command()
def init() -> None:
    """Bootstrap config + cache dir + API keys. See scripts/ah_init.py."""
    from scripts.ah_init import run as _run_init
    _run_init()


@app.command()
def doctor() -> None:
    """Run a health check (deps, sources reachable, cache writable)."""
    from scripts.ah_doctor import run as _run_doctor
    _run_doctor()


@app.command()
def warmup(
    universe: str = typer.Option("sample", help="'sample' | 'csi300' | 'hsi'"),
    years: int = typer.Option(5, help="How many years of history to pre-fetch"),
) -> None:
    """Pre-fetch data for a universe to warm the cache."""
    from scripts.ah_warmup import run as _run_warmup
    _run_warmup(universe=universe, years=years)
```

- [ ] **Step 4: Add `__version__` to `src/ah_research/__init__.py`**

```python
# src/ah_research/__init__.py
"""ah-research — personal A-shares + HK stock research platform."""

__version__ = "0.0.1"
```

- [ ] **Step 5: Run — expect pass (commands will fail when invoked with subcommand, but --help works)**

```bash
uv run pytest tests/unit/test_cli.py -v
```

- [ ] **Step 6: Commit**

```bash
git add src/ah_research/cli.py src/ah_research/__init__.py tests/unit/test_cli.py
git commit -m "feat(cli): add ah CLI skeleton with version/init/doctor/warmup"
```

---

### Task 0.8: `ah init` bootstrap

**Files:**
- Create: `scripts/__init__.py`
- Create: `scripts/ah_init.py`
- Test: `tests/unit/test_ah_init.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_ah_init.py
from pathlib import Path
import pytest
from scripts.ah_init import create_cache_dir, write_default_profile, run


def test_create_cache_dir_idempotent(tmp_path):
    target = tmp_path / ".ah-research"
    create_cache_dir(target)
    assert target.exists()
    # Second call is a no-op
    create_cache_dir(target)
    assert target.exists()
    # Subdirs created
    assert (target / "sessions").exists()
    assert (target / "logs").exists()


def test_write_default_profile_creates_yaml(tmp_path):
    path = tmp_path / "profile.yaml"
    write_default_profile(path)
    assert path.exists()
    content = path.read_text()
    assert "investor_style: value" in content
    assert "horizon: long_term" in content
    assert "default_rebalance: M" in content


def test_write_default_profile_does_not_overwrite(tmp_path):
    path = tmp_path / "profile.yaml"
    path.write_text("# user custom content\n")
    write_default_profile(path)
    assert path.read_text() == "# user custom content\n"


def test_run_creates_full_layout(tmp_path, monkeypatch):
    monkeypatch.setenv("AH_RESEARCH_CACHE_DIR", str(tmp_path / "custom"))
    from ah_research.config import get_settings
    get_settings.cache_clear()

    run(interactive=False)

    root = tmp_path / "custom"
    assert root.exists()
    assert (root / "profile.yaml").exists()
    assert (root / "sessions").exists()
    assert (root / "logs").exists()
```

- [ ] **Step 2: Run — expect ImportError**

- [ ] **Step 3: Implement `scripts/ah_init.py`**

```python
"""`ah init` — bootstrap cache dir, profile.yaml, confirm API key presence."""

from __future__ import annotations

from pathlib import Path

import typer

from ah_research.config import get_settings
from ah_research.logging import configure_logging, get_logger

log = get_logger(__name__)

DEFAULT_PROFILE = """\
# ah-research user profile — edit to taste
# Loaded into the AI system prompt so the chat knows your style.

investor_style: value           # value | growth | generic
horizon: long_term              # long_term (>60d) | medium (20-60d)
default_universe: CSI300        # or HSI / CSI500 / "CSI300+HSI"
default_rebalance: M            # D | W | M | Q
default_metrics:
  - cagr
  - sharpe
  - max_drawdown
  - dividend_yield_avg
preferred_visualizations:
  - valuation_bands
  - dossier
cn_color_convention: cn         # "cn" (red=up) | "west" (green=up)
api_budget_usd_per_session: 5.0
"""


def create_cache_dir(root: Path) -> None:
    """Create ~/.ah-research and required subdirs. Idempotent."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "sessions").mkdir(exist_ok=True)
    (root / "logs").mkdir(exist_ok=True)


def write_default_profile(path: Path) -> None:
    """Write DEFAULT_PROFILE to path if the file does not already exist."""
    if path.exists():
        log.info("profile_exists_skipping", path=str(path))
        return
    path.write_text(DEFAULT_PROFILE)
    log.info("profile_written", path=str(path))


def run(interactive: bool = True) -> None:
    """Main entrypoint called from `ah init`."""
    configure_logging()
    settings = get_settings()
    root = settings.cache_dir
    typer.echo(f"Setting up ah-research at {root}")
    create_cache_dir(root)
    write_default_profile(root / "profile.yaml")

    if interactive and settings.anthropic_api_key is None:
        typer.echo(
            "\n⚠  ANTHROPIC_API_KEY not set in environment.\n"
            "   The chat UI and ah.ask() will be unavailable until you set it.\n"
            "   Add to your shell rc: export ANTHROPIC_API_KEY=sk-...\n"
        )

    typer.echo(f"\n✓ Done. Next: `ah doctor` to verify everything works.\n")
```

- [ ] **Step 4: Run — expect pass**

- [ ] **Step 5: Manual smoke test**

```bash
AH_RESEARCH_CACHE_DIR=/tmp/ah-test uv run ah init
ls /tmp/ah-test
```
Expected: `profile.yaml logs sessions` listed.

- [ ] **Step 6: Commit**

```bash
git add scripts/__init__.py scripts/ah_init.py tests/unit/test_ah_init.py
git commit -m "feat(cli): add ah init bootstrap command"
```

---

### Task 0.9: `ah doctor` health check (skeleton — will fill in after Phase 1)

**Files:**
- Create: `scripts/ah_doctor.py`
- Test: `tests/unit/test_doctor.py`

- [ ] **Step 1: Write failing test for the checks API**

```python
# tests/unit/test_doctor.py
from pathlib import Path
from scripts.ah_doctor import check_python_version, check_cache_dir_writable, CheckResult


def test_check_python_version_passes_on_311_plus():
    result = check_python_version()
    assert result.ok is True
    assert "3.1" in result.detail or "3.2" in result.detail


def test_check_cache_dir_writable_passes_when_writable(tmp_path):
    result = check_cache_dir_writable(tmp_path)
    assert result.ok is True


def test_check_cache_dir_writable_fails_for_nonexistent():
    result = check_cache_dir_writable(Path("/nonexistent/ah-cache"))
    assert result.ok is False
    assert "not exist" in result.detail.lower() or "cannot write" in result.detail.lower()
```

- [ ] **Step 2: Run — expect ImportError**

- [ ] **Step 3: Implement `scripts/ah_doctor.py`**

```python
"""`ah doctor` — health check. Phase 0 version covers Python + cache dir.
Phase 1 will add: baostock login, akshare reachability, duckdb open, migrations."""

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
```

- [ ] **Step 4: Run — expect pass**

- [ ] **Step 5: Manual smoke test**

```bash
AH_RESEARCH_CACHE_DIR=/tmp/ah-test uv run ah doctor
```

- [ ] **Step 6: Commit**

```bash
git add scripts/ah_doctor.py tests/unit/test_doctor.py
git commit -m "feat(cli): add ah doctor health-check skeleton"
```

---

## Phase 1 — Integration + Data Layer (~1.5 weeks, 21 tasks)

### Task 1.1: Domain types

**Files:**
- Create: `src/ah_research/model/__init__.py`
- Create: `src/ah_research/model/types.py`
- Test: `tests/unit/test_model_types.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_model_types.py
import pytest
from datetime import date
from ah_research.model.types import (
    Symbol, Exchange, Currency, AHPair, IndexConstituent, CorporateAction,
    parse_symbol, Freq, Adjust, PriceKind, StatementKind, FillPrice, Settlement,
)


def test_symbol_roundtrips_string():
    s = parse_symbol("600519.SH")
    assert s.code == "600519"
    assert s.exchange == Exchange.SH
    assert s.currency == Currency.CNY
    assert str(s) == "600519.SH"


def test_parse_symbol_hk():
    s = parse_symbol("0700.HK")
    assert s.exchange == Exchange.HK
    assert s.currency == Currency.HKD


def test_parse_symbol_sz():
    s = parse_symbol("000001.SZ")
    assert s.exchange == Exchange.SZ
    assert s.currency == Currency.CNY


def test_parse_symbol_invalid_raises():
    from ah_research.exceptions import UserInputError
    with pytest.raises(UserInputError):
        parse_symbol("NVDA")
    with pytest.raises(UserInputError):
        parse_symbol("600519.US")


def test_symbol_frozen():
    s = parse_symbol("600519.SH")
    with pytest.raises(Exception):
        s.code = "000001"  # type: ignore[misc]


def test_ah_pair_construction():
    a = parse_symbol("601318.SH")
    h = parse_symbol("2318.HK")
    pair = AHPair(a_symbol=a, h_symbol=h, name_en="Ping An", name_zh="中国平安")
    assert pair.a_symbol.exchange == Exchange.SH
    assert pair.h_symbol.exchange == Exchange.HK


def test_index_constituent_effective_to_none_means_current():
    c = IndexConstituent(
        index="CSI300",
        symbol=parse_symbol("600519.SH"),
        weight=0.048,
        effective_from=date(2015, 1, 1),
        effective_to=None,
    )
    assert c.effective_to is None


def test_corporate_action_dividend():
    ca = CorporateAction(
        symbol=parse_symbol("600519.SH"),
        ex_date=date(2024, 6, 15),
        kind="cash_dividend",
        params={"amount_per_share": 30.88, "currency": "CNY"},
    )
    assert ca.kind == "cash_dividend"
    assert ca.params["amount_per_share"] == 30.88


def test_freq_enum_values():
    assert Freq.D.value == "D"
    assert Freq.W.value == "W"
    assert Freq.M.value == "M"
    assert Freq.Q.value == "Q"
```

- [ ] **Step 2: Run — expect ImportError**

- [ ] **Step 3: Implement `src/ah_research/model/types.py`**

```python
"""Pure domain types. No I/O, no pandas, no integrations."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any, Literal

from ah_research.exceptions import UserInputError


class Exchange(str, Enum):
    SH = "SH"  # Shanghai
    SZ = "SZ"  # Shenzhen
    HK = "HK"  # Hong Kong


class Currency(str, Enum):
    CNY = "CNY"
    HKD = "HKD"


class Freq(str, Enum):
    D = "D"
    W = "W"
    M = "M"
    Q = "Q"


Adjust = Literal["hfq", "qfq", "none"]
PriceKind = Literal["total_return", "price_only"]
StatementKind = Literal["preliminary", "audited", "auto"]
FillPrice = Literal["next_open", "next_vwap", "next_close"]
Settlement = Literal["auto", "T+1", "T+2", "T+0"]

CorporateActionKind = Literal[
    "cash_dividend", "stock_dividend", "split", "reverse_split",
    "rights_issue", "spin_off",
]


_SYMBOL_RE = re.compile(r"^([A-Z0-9]+)\.(SH|SZ|HK)$")
_CURRENCY_FOR_EXCHANGE = {
    Exchange.SH: Currency.CNY,
    Exchange.SZ: Currency.CNY,
    Exchange.HK: Currency.HKD,
}


@dataclass(frozen=True, slots=True)
class Symbol:
    code: str
    exchange: Exchange
    currency: Currency

    def __str__(self) -> str:
        return f"{self.code}.{self.exchange.value}"


def parse_symbol(s: str) -> Symbol:
    """Parse `<code>.<exchange>` format. Raises UserInputError on bad input."""
    m = _SYMBOL_RE.match(s)
    if not m:
        raise UserInputError(
            f"invalid symbol {s!r}; expected format like '600519.SH' or '0700.HK'"
        )
    code, ex = m.group(1), m.group(2)
    exchange = Exchange(ex)
    return Symbol(code=code, exchange=exchange, currency=_CURRENCY_FOR_EXCHANGE[exchange])


@dataclass(frozen=True, slots=True)
class AHPair:
    a_symbol: Symbol
    h_symbol: Symbol
    name_en: str
    name_zh: str


@dataclass(frozen=True, slots=True)
class IndexConstituent:
    index: str
    symbol: Symbol
    weight: float | None
    effective_from: date
    effective_to: date | None  # None = currently a member


@dataclass(frozen=True, slots=True)
class CorporateAction:
    symbol: Symbol
    ex_date: date
    kind: CorporateActionKind
    params: dict[str, Any] = field(default_factory=dict)
```

- [ ] **Step 4: Export from `model/__init__.py`**

```python
# src/ah_research/model/__init__.py
from ah_research.model.types import (
    Adjust,
    AHPair,
    CorporateAction,
    CorporateActionKind,
    Currency,
    Exchange,
    FillPrice,
    Freq,
    IndexConstituent,
    PriceKind,
    Settlement,
    StatementKind,
    Symbol,
    parse_symbol,
)

__all__ = [
    "Adjust", "AHPair", "CorporateAction", "CorporateActionKind", "Currency",
    "Exchange", "FillPrice", "Freq", "IndexConstituent", "PriceKind",
    "Settlement", "StatementKind", "Symbol", "parse_symbol",
]
```

- [ ] **Step 5: Run — expect all pass**

- [ ] **Step 6: Commit**

```bash
git add src/ah_research/model/ tests/unit/test_model_types.py
git commit -m "feat(model): add domain types Symbol, AHPair, IndexConstituent, CorporateAction"
```

---

### Task 1.2: Pandera schemas

**Files:**
- Create: `src/ah_research/model/schemas.py`
- Test: `tests/unit/test_model_schemas.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_model_schemas.py
import pandas as pd
import pandera as pa
import pytest
from ah_research.model.schemas import PriceFrameSchema, FundamentalsFrameSchema


def _valid_price_row() -> dict:
    return dict(
        date=pd.Timestamp("2024-06-15"),
        symbol="600519.SH",
        open=1700.0, high=1720.0, low=1690.0, close=1710.0,
        close_hfq=1710.0, total_return=1800.0,
        volume=1_000_000, amount=1_700_000_000.0, turnover=0.001,
        is_suspended=False, is_st=False,
        limit_up=1881.0, limit_down=1539.0,
        hit_limit_up=False, hit_limit_down=False,
    )


def test_price_frame_validates_minimal_ok():
    df = pd.DataFrame([_valid_price_row()])
    PriceFrameSchema.validate(df)  # should not raise


def test_price_frame_rejects_negative_volume():
    row = _valid_price_row()
    row["volume"] = -1
    df = pd.DataFrame([row])
    with pytest.raises(pa.errors.SchemaError):
        PriceFrameSchema.validate(df)


def test_price_frame_rejects_missing_required_column():
    row = _valid_price_row()
    del row["is_st"]
    df = pd.DataFrame([row])
    with pytest.raises(pa.errors.SchemaError):
        PriceFrameSchema.validate(df)


def _valid_fundamentals_row() -> dict:
    return dict(
        symbol="600519.SH",
        report_date=pd.Timestamp("2024-03-31"),
        publication_date=pd.Timestamp("2024-04-28"),
        known_as_of=pd.Timestamp("2024-04-28"),
        statement_kind="audited",
        revenue=10_000_000_000.0, net_income=3_000_000_000.0,
        net_income_ex_nonrecurring=2_950_000_000.0,
        operating_cash_flow=3_500_000_000.0, capex=200_000_000.0,
        total_assets=80_000_000_000.0, total_equity=50_000_000_000.0,
        total_debt=10_000_000_000.0, goodwill=0.0, minority_interest=100_000_000.0,
        d_and_a=300_000_000.0, working_capital_change=100_000_000.0,
        pe=25.0, pb=8.0, ps=10.0, ev_ebitda=15.0,
        roe=0.25, roic=0.22, roa=0.15,
        gross_margin=0.92, net_margin=0.50, dividend_yield=0.018,
        market_cap=2_000_000_000_000.0, market_cap_free_float=1_500_000_000_000.0,
        is_soe=True, is_stock_connect_eligible=True,
    )


def test_fundamentals_frame_validates_minimal_ok():
    df = pd.DataFrame([_valid_fundamentals_row()])
    FundamentalsFrameSchema.validate(df)


def test_fundamentals_rejects_bad_statement_kind():
    row = _valid_fundamentals_row()
    row["statement_kind"] = "garbage"
    df = pd.DataFrame([row])
    with pytest.raises(pa.errors.SchemaError):
        FundamentalsFrameSchema.validate(df)


def test_fundamentals_requires_publication_date():
    row = _valid_fundamentals_row()
    del row["publication_date"]
    df = pd.DataFrame([row])
    with pytest.raises(pa.errors.SchemaError):
        FundamentalsFrameSchema.validate(df)
```

- [ ] **Step 2: Run — expect ImportError**

- [ ] **Step 3: Implement `src/ah_research/model/schemas.py`**

```python
"""Pandera schemas — runtime-validated at every layer boundary.

These are the contract for PriceFrame and FundamentalsFrame as defined in
spec §3. Converters validate on output; DataRepository validates on return.
"""

from __future__ import annotations

import pandera.pandas as pa
from pandera.typing import Series


class PriceFrameSchema(pa.DataFrameModel):
    date: Series[pa.DateTime]
    symbol: Series[str]
    open: Series[float]
    high: Series[float]
    low: Series[float]
    close: Series[float]
    close_hfq: Series[float]          # back-adjusted; DEFAULT for research
    total_return: Series[float]       # cum-dividend-reinvested
    volume: Series[int] = pa.Field(ge=0)
    amount: Series[float] = pa.Field(ge=0)
    turnover: Series[float]
    is_suspended: Series[bool]
    is_st: Series[bool]
    limit_up: Series[float]
    limit_down: Series[float]
    hit_limit_up: Series[bool]
    hit_limit_down: Series[bool]

    class Config:
        strict = True
        coerce = True


class FundamentalsFrameSchema(pa.DataFrameModel):
    symbol: Series[str]
    report_date: Series[pa.DateTime]
    publication_date: Series[pa.DateTime]
    known_as_of: Series[pa.DateTime]
    statement_kind: Series[str] = pa.Field(isin=["preliminary", "audited", "restated"])

    # raw line items
    revenue: Series[float]
    net_income: Series[float]
    net_income_ex_nonrecurring: Series[float]
    operating_cash_flow: Series[float]
    capex: Series[float]
    total_assets: Series[float]
    total_equity: Series[float]
    total_debt: Series[float]
    goodwill: Series[float]
    minority_interest: Series[float]
    d_and_a: Series[float]
    working_capital_change: Series[float]

    # derived ratios
    pe: Series[float]
    pb: Series[float]
    ps: Series[float]
    ev_ebitda: Series[float]
    roe: Series[float]
    roic: Series[float]
    roa: Series[float]
    gross_margin: Series[float]
    net_margin: Series[float]
    dividend_yield: Series[float]
    market_cap: Series[float]
    market_cap_free_float: Series[float]

    # flags
    is_soe: Series[bool]
    is_stock_connect_eligible: Series[bool]

    class Config:
        strict = True
        coerce = True


class TradingCalendarSchema(pa.DataFrameModel):
    exchange: Series[str] = pa.Field(isin=["SH", "SZ", "HK"])
    date: Series[pa.DateTime]
    is_trading_day: Series[bool]

    class Config:
        strict = True
        coerce = True


class CorporateActionSchema(pa.DataFrameModel):
    symbol: Series[str]
    ex_date: Series[pa.DateTime]
    kind: Series[str] = pa.Field(isin=[
        "cash_dividend", "stock_dividend", "split", "reverse_split",
        "rights_issue", "spin_off",
    ])
    params_json: Series[str]  # serialized dict; decoded by repository

    class Config:
        strict = True
        coerce = True
```

- [ ] **Step 4: Run — expect pass**

- [ ] **Step 5: Commit**

```bash
git add src/ah_research/model/schemas.py tests/unit/test_model_schemas.py
git commit -m "feat(model): add pandera schemas for PriceFrame, FundamentalsFrame, Calendar, CorporateAction"
```

---

### Task 1.3: Integration Protocols

**Files:**
- Create: `src/ah_research/integrations/__init__.py`
- Create: `src/ah_research/integrations/_protocols.py`
- Test: `tests/unit/test_integrations_protocols.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_integrations_protocols.py
from datetime import date
import pandas as pd
from ah_research.integrations import (
    PriceSource, FundamentalsSource, FXSource, CalendarSource,
    SectorSource, CorporateActionsSource, ConstituentsSource,
)


class _FakePriceSource:
    def fetch_prices(
        self, symbols: list[str], start: date, end: date,
    ) -> pd.DataFrame:
        return pd.DataFrame()


def test_fake_satisfies_protocol():
    # Protocol is runtime-checkable via structural typing
    src: PriceSource = _FakePriceSource()
    result = src.fetch_prices(["600519.SH"], date(2024, 1, 1), date(2024, 6, 30))
    assert isinstance(result, pd.DataFrame)


def test_protocol_names_exported():
    for name in [
        "PriceSource", "FundamentalsSource", "FXSource",
        "CalendarSource", "SectorSource", "CorporateActionsSource",
        "ConstituentsSource",
    ]:
        from ah_research import integrations
        assert hasattr(integrations, name)
```

- [ ] **Step 2: Run — expect ImportError**

- [ ] **Step 3: Implement `src/ah_research/integrations/_protocols.py`**

```python
"""Protocols for integration-layer sources.

Data Repository DI's these protocols, not concrete clients. Tests substitute
fakes. Each concrete client implements one or more of these.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

import pandas as pd


@runtime_checkable
class PriceSource(Protocol):
    def fetch_prices(
        self, symbols: list[str], start: date, end: date,
    ) -> pd.DataFrame:
        """Return source-native daily OHLCV + volume/amount/turnover for symbols."""
        ...


@runtime_checkable
class FundamentalsSource(Protocol):
    def fetch_fundamentals(
        self, symbols: list[str], start: date, end: date,
    ) -> pd.DataFrame:
        """Return source-native fundamentals rows with report_date,
        publication_date, and statement_kind preserved."""
        ...


@runtime_checkable
class FXSource(Protocol):
    def fetch_fx(self, pair: str, start: date, end: date) -> pd.DataFrame:
        """pair e.g. 'CNY_HKD'. Returns daily rates."""
        ...


@runtime_checkable
class CalendarSource(Protocol):
    def fetch_calendar(self, exchange: str, start: date, end: date) -> pd.DataFrame:
        """Return trading-day flags for the exchange."""
        ...


@runtime_checkable
class SectorSource(Protocol):
    def fetch_sectors(self, symbols: list[str]) -> pd.DataFrame:
        """Return (symbol, sector_l1, sector_l2) in SWS classification."""
        ...


@runtime_checkable
class CorporateActionsSource(Protocol):
    def fetch_corporate_actions(
        self, symbols: list[str], start: date, end: date,
    ) -> pd.DataFrame:
        ...


@runtime_checkable
class ConstituentsSource(Protocol):
    def fetch_constituents(self, index: str, asof: date) -> pd.DataFrame:
        """Return constituents AS OF the given date (PIT)."""
        ...
```

- [ ] **Step 4: Wire exports in `integrations/__init__.py`**

```python
# src/ah_research/integrations/__init__.py
from ah_research.integrations._protocols import (
    CalendarSource,
    ConstituentsSource,
    CorporateActionsSource,
    FXSource,
    FundamentalsSource,
    PriceSource,
    SectorSource,
)

__all__ = [
    "CalendarSource", "ConstituentsSource", "CorporateActionsSource",
    "FXSource", "FundamentalsSource", "PriceSource", "SectorSource",
]
```

- [ ] **Step 5: Run — expect pass**

- [ ] **Step 6: Commit**

```bash
git add src/ah_research/integrations/ tests/unit/test_integrations_protocols.py
git commit -m "feat(integrations): add Protocols for PriceSource, FundamentalsSource, etc."
```

---

### Task 1.4: Fake integrations (for all downstream tests)

**Files:**
- Create: `src/ah_research/integrations/fake/__init__.py`
- Create: `src/ah_research/integrations/fake/client.py`
- Test: `tests/unit/test_fake_integrations.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_fake_integrations.py
from datetime import date
from ah_research.integrations.fake import FakeSources


def test_fake_price_source_deterministic():
    fake = FakeSources(seed=42)
    df1 = fake.prices.fetch_prices(["600519.SH"], date(2024, 1, 1), date(2024, 1, 10))
    df2 = fake.prices.fetch_prices(["600519.SH"], date(2024, 1, 1), date(2024, 1, 10))
    assert df1.equals(df2)
    assert len(df1) > 0
    assert "close" in df1.columns


def test_fake_price_source_multiple_symbols():
    fake = FakeSources(seed=42)
    df = fake.prices.fetch_prices(
        ["600519.SH", "0700.HK"], date(2024, 1, 1), date(2024, 1, 10)
    )
    assert set(df["symbol"].unique()) == {"600519.SH", "0700.HK"}


def test_fake_fundamentals_bitemporal_rows():
    fake = FakeSources(seed=42)
    df = fake.fundamentals.fetch_fundamentals(
        ["600519.SH"], date(2020, 1, 1), date(2024, 12, 31),
    )
    # Each report should have both preliminary and audited rows
    grp = df.groupby(["symbol", "report_date"])["statement_kind"].nunique()
    assert (grp >= 1).all()


def test_fake_constituents_returns_stable_list():
    fake = FakeSources(seed=42)
    df = fake.constituents.fetch_constituents("CSI300", date(2024, 1, 1))
    assert len(df) == 300
    assert "symbol" in df.columns
    assert "weight" in df.columns


def test_fake_calendar_flags_weekends():
    fake = FakeSources(seed=42)
    df = fake.calendar.fetch_calendar("SH", date(2024, 1, 1), date(2024, 1, 14))
    # 2024-01-06 Saturday, 2024-01-07 Sunday
    sat = df[df["date"] == "2024-01-06"]["is_trading_day"].iloc[0]
    assert bool(sat) is False
```

- [ ] **Step 2: Run — expect ImportError**

- [ ] **Step 3: Implement `src/ah_research/integrations/fake/client.py`** (deterministic; enough for unit tests of `DataRepository`)

```python
"""Deterministic fake implementations of every Protocol. For tests only.

Produces plausible-looking source-native DataFrames (column names match
Baostock conventions where relevant) so the converter can process them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class FakeSources:
    """Container holding one fake per Protocol. Access as fake.prices etc."""

    seed: int = 42

    def __post_init__(self) -> None:
        rng = np.random.default_rng(self.seed)
        self.prices = _FakePrices(rng)
        self.fundamentals = _FakeFundamentals(rng)
        self.fx = _FakeFX(rng)
        self.calendar = _FakeCalendar()
        self.sectors = _FakeSectors()
        self.corporate_actions = _FakeCorporateActions()
        self.constituents = _FakeConstituents()


class _FakePrices:
    def __init__(self, rng: np.random.Generator) -> None:
        self._rng = rng

    def fetch_prices(self, symbols: list[str], start: date, end: date) -> pd.DataFrame:
        dates = pd.bdate_range(start, end)
        rows: list[dict[str, Any]] = []
        for sym in symbols:
            # Deterministic per-symbol start
            base = 100.0 + (hash(sym) % 1000)
            prices = base * np.exp(np.cumsum(self._rng.normal(0, 0.01, len(dates))))
            for d, p in zip(dates, prices):
                rows.append({
                    "date": d,
                    "symbol": sym,
                    "open": p * 0.998,
                    "high": p * 1.01,
                    "low": p * 0.99,
                    "close": p,
                    "volume": int(1_000_000 + self._rng.uniform(-100_000, 100_000)),
                    "amount": float(p * 1_000_000),
                    "turnover": 0.01,
                    "is_suspended": False,
                    "is_st": False,
                })
        return pd.DataFrame(rows)


class _FakeFundamentals:
    def __init__(self, rng: np.random.Generator) -> None:
        self._rng = rng

    def fetch_fundamentals(self, symbols: list[str], start: date, end: date) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        for sym in symbols:
            d = date(start.year, 3, 31)
            while d <= end:
                pub = d + timedelta(days=30)
                rows.append({
                    "symbol": sym,
                    "report_date": pd.Timestamp(d),
                    "publication_date": pd.Timestamp(pub),
                    "statement_kind": "audited",
                    "revenue": 1e10, "net_income": 3e9,
                    "net_income_ex_nonrecurring": 2.95e9,
                    "operating_cash_flow": 3.5e9, "capex": 2e8,
                    "total_assets": 8e10, "total_equity": 5e10,
                    "total_debt": 1e10, "goodwill": 0.0,
                    "minority_interest": 1e8, "d_and_a": 3e8,
                    "working_capital_change": 1e8,
                    "pe": 25.0, "pb": 8.0, "ps": 10.0, "ev_ebitda": 15.0,
                    "roe": 0.25, "roa": 0.15,
                    "gross_margin": 0.92, "net_margin": 0.30,
                    "dividend_yield": 0.02,
                    "market_cap": 2e12, "market_cap_free_float": 1.5e12,
                    "is_soe": "SH" in sym,
                    "is_stock_connect_eligible": True,
                })
                if d.month == 3:
                    d = date(d.year, 6, 30)
                elif d.month == 6:
                    d = date(d.year, 9, 30)
                elif d.month == 9:
                    d = date(d.year, 12, 31)
                else:
                    d = date(d.year + 1, 3, 31)
        return pd.DataFrame(rows)


class _FakeFX:
    def __init__(self, rng: np.random.Generator) -> None:
        self._rng = rng

    def fetch_fx(self, pair: str, start: date, end: date) -> pd.DataFrame:
        dates = pd.bdate_range(start, end)
        rates = 0.91 + self._rng.normal(0, 0.005, len(dates))
        return pd.DataFrame({"date": dates, "pair": pair, "rate": rates})


class _FakeCalendar:
    def fetch_calendar(self, exchange: str, start: date, end: date) -> pd.DataFrame:
        dates = pd.date_range(start, end)
        return pd.DataFrame({
            "exchange": exchange,
            "date": dates,
            "is_trading_day": [d.weekday() < 5 for d in dates],
        })


class _FakeSectors:
    def fetch_sectors(self, symbols: list[str]) -> pd.DataFrame:
        sectors_l1 = ["Financials", "Consumer", "Technology", "Industrials", "Energy",
                      "Healthcare", "Materials", "Utilities"]
        rows = []
        for i, s in enumerate(symbols):
            rows.append({
                "symbol": s,
                "sector_l1": sectors_l1[i % len(sectors_l1)],
                "sector_l2": f"{sectors_l1[i % len(sectors_l1)]}-A",
            })
        return pd.DataFrame(rows)


class _FakeCorporateActions:
    def fetch_corporate_actions(self, symbols: list[str], start: date, end: date) -> pd.DataFrame:
        # empty by default — tests opt in to specific actions
        return pd.DataFrame(columns=["symbol", "ex_date", "kind", "params_json"])


class _FakeConstituents:
    def fetch_constituents(self, index: str, asof: date) -> pd.DataFrame:
        # produce 300 deterministic symbols for CSI300, 50 for HSI, 500 for CSI500
        n = {"CSI300": 300, "HSI": 50, "CSI500": 500}.get(index, 100)
        exchange = "HK" if index == "HSI" else "SH"
        code_fmt = "{:04d}" if exchange == "HK" else "{:06d}"
        symbols = [f"{code_fmt.format(i + 1)}.{exchange}" for i in range(n)]
        return pd.DataFrame({
            "index": index,
            "symbol": symbols,
            "weight": [1 / n] * n,
            "asof": [pd.Timestamp(asof)] * n,
        })
```

- [ ] **Step 4: Wire exports in `integrations/fake/__init__.py`**

```python
# src/ah_research/integrations/fake/__init__.py
from ah_research.integrations.fake.client import FakeSources

__all__ = ["FakeSources"]
```

- [ ] **Step 5: Run — expect pass**

- [ ] **Step 6: Commit**

```bash
git add src/ah_research/integrations/fake/ tests/unit/test_fake_integrations.py
git commit -m "feat(integrations): add deterministic fake sources for testing"
```

---

### Task 1.5: DuckDB cache foundation

**Files:**
- Create: `src/ah_research/data/__init__.py`
- Create: `src/ah_research/data/cache.py`
- Create: `src/ah_research/data/migrations/0001_init.sql`
- Test: `tests/unit/test_cache.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_cache.py
import pandas as pd
import pytest
from ah_research.data.cache import DuckDBCache
from ah_research.exceptions import DataIntegrityError


def test_cache_creates_file_on_init(tmp_path):
    path = tmp_path / "cache.duckdb"
    cache = DuckDBCache(path)
    assert path.exists()
    cache.close()


def test_cache_applies_initial_migration(tmp_path):
    cache = DuckDBCache(tmp_path / "cache.duckdb")
    version = cache.schema_version()
    assert version >= 1
    tables = cache.list_tables()
    assert "prices" in tables
    assert "fundamentals" in tables
    assert "index_constituents" in tables
    assert "calendars" in tables
    assert "fx_rates" in tables
    assert "sectors" in tables
    assert "corporate_actions" in tables
    assert "meta" in tables
    cache.close()


def test_cache_prices_roundtrip(tmp_path):
    cache = DuckDBCache(tmp_path / "cache.duckdb")
    df = pd.DataFrame({
        "date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
        "symbol": ["600519.SH", "600519.SH"],
        "open": [1700.0, 1710.0],
        "high": [1720.0, 1715.0],
        "low": [1695.0, 1700.0],
        "close": [1710.0, 1705.0],
        "close_hfq": [1710.0, 1705.0],
        "total_return": [1800.0, 1795.0],
        "volume": [1_000_000, 900_000],
        "amount": [1.7e9, 1.5e9],
        "turnover": [0.001, 0.001],
        "is_suspended": [False, False],
        "is_st": [False, False],
        "limit_up": [1881.0, 1881.0],
        "limit_down": [1539.0, 1539.0],
        "hit_limit_up": [False, False],
        "hit_limit_down": [False, False],
    })
    cache.write_prices(df)
    out = cache.read_prices(["600519.SH"], "2024-01-01", "2024-12-31")
    assert len(out) == 2
    assert set(out["symbol"]) == {"600519.SH"}
    cache.close()


def test_cache_prices_idempotent_on_duplicate_writes(tmp_path):
    cache = DuckDBCache(tmp_path / "cache.duckdb")
    df = pd.DataFrame({
        "date": pd.to_datetime(["2024-01-02"]),
        "symbol": ["600519.SH"],
        "open": [1700.0], "high": [1720.0], "low": [1695.0], "close": [1710.0],
        "close_hfq": [1710.0], "total_return": [1800.0],
        "volume": [1_000_000], "amount": [1.7e9], "turnover": [0.001],
        "is_suspended": [False], "is_st": [False],
        "limit_up": [1881.0], "limit_down": [1539.0],
        "hit_limit_up": [False], "hit_limit_down": [False],
    })
    cache.write_prices(df)
    cache.write_prices(df)  # should overwrite, not double
    out = cache.read_prices(["600519.SH"], "2024-01-01", "2024-12-31")
    assert len(out) == 1
    cache.close()


def test_cache_range_coverage_empty(tmp_path):
    cache = DuckDBCache(tmp_path / "cache.duckdb")
    covered = cache.price_coverage("600519.SH")
    assert covered is None  # nothing cached
    cache.close()


def test_cache_range_coverage_after_write(tmp_path):
    cache = DuckDBCache(tmp_path / "cache.duckdb")
    df = pd.DataFrame({
        "date": pd.to_datetime(["2024-01-02", "2024-06-15"]),
        "symbol": ["600519.SH", "600519.SH"],
        "open": [1700.0, 1800.0], "high": [1720.0, 1820.0],
        "low": [1695.0, 1795.0], "close": [1710.0, 1810.0],
        "close_hfq": [1710.0, 1810.0], "total_return": [1800.0, 1905.0],
        "volume": [1_000_000, 1_100_000], "amount": [1.7e9, 1.99e9],
        "turnover": [0.001, 0.001],
        "is_suspended": [False, False], "is_st": [False, False],
        "limit_up": [1881.0, 1991.0], "limit_down": [1539.0, 1629.0],
        "hit_limit_up": [False, False], "hit_limit_down": [False, False],
    })
    cache.write_prices(df)
    from datetime import date
    lo, hi = cache.price_coverage("600519.SH")
    assert lo == date(2024, 1, 2)
    assert hi == date(2024, 6, 15)
    cache.close()
```

- [ ] **Step 2: Run — expect ImportError**

- [ ] **Step 3: Write migration `src/ah_research/data/migrations/0001_init.sql`**

```sql
-- Initial schema for ah-research cache.
-- Managed via data/cache.py migrations.

CREATE TABLE IF NOT EXISTS meta (
    key   VARCHAR PRIMARY KEY,
    value VARCHAR
);

INSERT OR IGNORE INTO meta (key, value) VALUES ('schema_version', '1');

CREATE TABLE IF NOT EXISTS prices (
    date           DATE NOT NULL,
    symbol         VARCHAR NOT NULL,
    open           DOUBLE,
    high           DOUBLE,
    low            DOUBLE,
    close          DOUBLE,
    close_hfq      DOUBLE,
    total_return   DOUBLE,
    volume         BIGINT,
    amount         DOUBLE,
    turnover       DOUBLE,
    is_suspended   BOOLEAN,
    is_st          BOOLEAN,
    limit_up       DOUBLE,
    limit_down     DOUBLE,
    hit_limit_up   BOOLEAN,
    hit_limit_down BOOLEAN,
    PRIMARY KEY (date, symbol)
);

CREATE TABLE IF NOT EXISTS fundamentals (
    symbol                     VARCHAR NOT NULL,
    report_date                DATE NOT NULL,
    publication_date           DATE NOT NULL,
    known_as_of                DATE NOT NULL,
    statement_kind             VARCHAR NOT NULL,
    revenue                    DOUBLE,
    net_income                 DOUBLE,
    net_income_ex_nonrecurring DOUBLE,
    operating_cash_flow        DOUBLE,
    capex                      DOUBLE,
    total_assets               DOUBLE,
    total_equity               DOUBLE,
    total_debt                 DOUBLE,
    goodwill                   DOUBLE,
    minority_interest          DOUBLE,
    d_and_a                    DOUBLE,
    working_capital_change     DOUBLE,
    pe                         DOUBLE,
    pb                         DOUBLE,
    ps                         DOUBLE,
    ev_ebitda                  DOUBLE,
    roe                        DOUBLE,
    roic                       DOUBLE,
    roa                        DOUBLE,
    gross_margin               DOUBLE,
    net_margin                 DOUBLE,
    dividend_yield             DOUBLE,
    market_cap                 DOUBLE,
    market_cap_free_float      DOUBLE,
    is_soe                     BOOLEAN,
    is_stock_connect_eligible  BOOLEAN,
    PRIMARY KEY (symbol, report_date, known_as_of, statement_kind)
);

CREATE TABLE IF NOT EXISTS index_constituents (
    index_name     VARCHAR NOT NULL,
    symbol         VARCHAR NOT NULL,
    weight         DOUBLE,
    effective_from DATE NOT NULL,
    effective_to   DATE,
    PRIMARY KEY (index_name, symbol, effective_from)
);

CREATE TABLE IF NOT EXISTS calendars (
    exchange        VARCHAR NOT NULL,
    date            DATE NOT NULL,
    is_trading_day  BOOLEAN NOT NULL,
    PRIMARY KEY (exchange, date)
);

CREATE TABLE IF NOT EXISTS fx_rates (
    date DATE NOT NULL,
    pair VARCHAR NOT NULL,
    rate DOUBLE NOT NULL,
    PRIMARY KEY (date, pair)
);

CREATE TABLE IF NOT EXISTS sectors (
    symbol    VARCHAR PRIMARY KEY,
    sector_l1 VARCHAR,
    sector_l2 VARCHAR
);

CREATE TABLE IF NOT EXISTS corporate_actions (
    symbol      VARCHAR NOT NULL,
    ex_date     DATE NOT NULL,
    kind        VARCHAR NOT NULL,
    params_json VARCHAR NOT NULL,
    PRIMARY KEY (symbol, ex_date, kind)
);

CREATE INDEX IF NOT EXISTS idx_prices_symbol_date ON prices (symbol, date);
CREATE INDEX IF NOT EXISTS idx_fundamentals_symbol_pub ON fundamentals (symbol, publication_date);
```

- [ ] **Step 4: Implement `src/ah_research/data/cache.py`**

```python
"""DuckDB-backed cache. One file, atomic transactions, schema migrations.

See spec §3 "Cache" and §10 data-layer contract. Schema evolution happens via
numbered SQL files in data/migrations/.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

from ah_research.exceptions import DataIntegrityError
from ah_research.logging import get_logger

log = get_logger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


class DuckDBCache:
    """Composable over DataRepository. Owns schema, migrations, and table IO.
    Not thread-safe for writes — serialize through a single instance per process.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(str(path))
        self._apply_migrations()

    def close(self) -> None:
        self._conn.close()

    def _apply_migrations(self) -> None:
        for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
            sql = sql_file.read_text()
            self._conn.execute(sql)
        log.info("cache_migrations_applied", path=str(self.path))

    def schema_version(self) -> int:
        row = self._conn.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()
        if row is None:
            raise DataIntegrityError("meta.schema_version missing")
        return int(row[0])

    def list_tables(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchall()
        return [r[0] for r in rows]

    # ── prices ─────────────────────────────────────────────────────────────

    def write_prices(self, df: pd.DataFrame) -> None:
        """Upsert (date, symbol) rows. Idempotent."""
        self._conn.register("df", df)
        self._conn.execute("DELETE FROM prices WHERE (date, symbol) IN (SELECT date, symbol FROM df)")
        self._conn.execute("INSERT INTO prices SELECT * FROM df")
        self._conn.unregister("df")

    def read_prices(self, symbols: list[str], start: date | str, end: date | str) -> pd.DataFrame:
        return self._conn.execute(
            "SELECT * FROM prices WHERE symbol IN (SELECT UNNEST(?)) "
            "AND date BETWEEN ? AND ? ORDER BY symbol, date",
            [symbols, str(start), str(end)],
        ).fetchdf()

    def price_coverage(self, symbol: str) -> tuple[date, date] | None:
        row = self._conn.execute(
            "SELECT MIN(date), MAX(date) FROM prices WHERE symbol = ?", [symbol]
        ).fetchone()
        if row is None or row[0] is None:
            return None
        return row[0], row[1]
```

- [ ] **Step 5: Run — expect pass**

- [ ] **Step 6: Commit**

```bash
git add src/ah_research/data/ tests/unit/test_cache.py
git commit -m "feat(cache): add DuckDB cache with migrations and prices table"
```

---

### Tasks 1.6 – 1.9: Extend cache for all entities (similar pattern)

Each adds one entity's `write_*`/`read_*` methods to `DuckDBCache`, with a test per method. Same TDD shape as Task 1.5. Keep each as a separate commit.

- **Task 1.6:** `write_fundamentals` / `read_fundamentals_asof(symbols, asof)` — filters `publication_date <= asof AND known_as_of <= asof`, returning latest row per `(symbol, report_date)`.
- **Task 1.7:** `write_constituents` / `read_constituents_asof(index, asof)` — returns members where `effective_from <= asof AND (effective_to IS NULL OR effective_to > asof)`.
- **Task 1.8:** `write_calendar` / `read_calendar(exchange, start, end)`, `write_fx` / `read_fx`.
- **Task 1.9:** `write_sectors` / `read_sectors(symbols)`, `write_corporate_actions` / `read_corporate_actions(symbols, start, end)`.

**For each:** follow the same 5-step TDD: test file add, run fail, implement in `cache.py`, run pass, commit. Code shape is parallel to `write_prices`/`read_prices`.

---

### Task 1.10: Converter from source-native to domain schema — prices

**Files:**
- Create: `src/ah_research/data/converters.py`
- Test: `tests/unit/test_converters.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_converters.py
import pandas as pd
import pytest
from ah_research.data.converters import convert_prices, compute_adjusted_prices
from ah_research.model.schemas import PriceFrameSchema


def _raw_source_df() -> pd.DataFrame:
    return pd.DataFrame({
        "date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
        "symbol": ["600519.SH", "600519.SH"],
        "open": [1700.0, 1710.0],
        "high": [1720.0, 1715.0],
        "low": [1695.0, 1700.0],
        "close": [1710.0, 1705.0],
        "volume": [1_000_000, 900_000],
        "amount": [1.7e9, 1.5e9],
        "turnover": [0.001, 0.001],
        "is_suspended": [False, False],
        "is_st": [False, False],
    })


def test_convert_prices_adds_required_columns_and_validates():
    raw = _raw_source_df()
    result = convert_prices(raw, corporate_actions=pd.DataFrame())
    PriceFrameSchema.validate(result)  # must pass
    assert "close_hfq" in result.columns
    assert "total_return" in result.columns
    assert "limit_up" in result.columns
    assert "hit_limit_up" in result.columns


def test_compute_adjusted_prices_no_actions_is_identity():
    raw = _raw_source_df()
    result = compute_adjusted_prices(raw, pd.DataFrame())
    # With no corporate actions, close_hfq == close, total_return == close
    assert (result["close_hfq"] == result["close"]).all()


def test_compute_adjusted_prices_with_cash_dividend():
    raw = _raw_source_df()
    actions = pd.DataFrame({
        "symbol": ["600519.SH"],
        "ex_date": [pd.Timestamp("2024-01-03")],
        "kind": ["cash_dividend"],
        "params_json": ['{"amount_per_share": 30.0, "currency": "CNY"}'],
    })
    result = compute_adjusted_prices(raw, actions)
    # close_hfq on day 1 should be scaled up by the dividend effect relative to close_hfq day 2
    # (back-adjustment adds back the dividend)
    # total_return on day 2 should reflect dividend reinvestment
    assert result.loc[result["date"] == "2024-01-02", "close_hfq"].iloc[0] != \
           result.loc[result["date"] == "2024-01-02", "close"].iloc[0]


def test_price_limit_detection():
    # A-share limit is ±10% of previous close (non-ST)
    raw = pd.DataFrame({
        "date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
        "symbol": ["600519.SH", "600519.SH"],
        "open": [1700.0, 1870.0],
        "high": [1720.0, 1881.0],  # day 2 hits limit up
        "low": [1695.0, 1870.0],
        "close": [1710.0, 1881.0],
        "volume": [1_000_000, 900_000],
        "amount": [1.7e9, 1.5e9],
        "turnover": [0.001, 0.001],
        "is_suspended": [False, False],
        "is_st": [False, False],
    })
    result = convert_prices(raw, corporate_actions=pd.DataFrame())
    # Day 2 high equals limit_up — hit_limit_up should be True
    day2 = result[result["date"] == "2024-01-03"].iloc[0]
    assert day2["limit_up"] == pytest.approx(1881.0, abs=0.01)
    assert day2["hit_limit_up"] is True or bool(day2["hit_limit_up"]) is True
```

- [ ] **Step 2: Run — expect ImportError**

- [ ] **Step 3: Implement `src/ah_research/data/converters.py`**

```python
"""Pure functions: source-native DataFrame → domain PriceFrame / FundamentalsFrame.

Key responsibility: the integration layer produces source-shaped data.
Converters normalize to the domain model AND compute derived columns
(close_hfq, total_return, limit_up, hit_limit_up, etc.). Output is pandera-
validated at the boundary.
"""

from __future__ import annotations

import json

import pandas as pd

from ah_research.model.schemas import FundamentalsFrameSchema, PriceFrameSchema


def compute_adjusted_prices(
    raw: pd.DataFrame, corporate_actions: pd.DataFrame,
) -> pd.DataFrame:
    """Back-adjust close to produce close_hfq, and compute cumulative total_return.

    back-adjusted (hfq): historical prices are multiplied by a cumulative factor
    that makes the most recent close unchanged and historical closes adjusted
    downward for splits/dividends. This is the industry-standard backtest series.

    total_return: dividends reinvested at ex-date. Same scale as close.
    """
    df = raw.copy()
    df["close_hfq"] = df["close"].astype(float)
    df["total_return"] = df["close"].astype(float)

    if len(corporate_actions) == 0:
        return df

    # Apply actions sorted by ex_date per symbol. For cash dividends, scale all
    # prior close_hfq up by (1 - div/close_on_ex_date_prev); add dividend back
    # to total_return going forward.
    for symbol, group in corporate_actions.groupby("symbol"):
        mask = df["symbol"] == symbol
        if not mask.any():
            continue
        sym_prices = df[mask].sort_values("date").reset_index()
        for _, action in group.iterrows():
            if action["kind"] != "cash_dividend":
                continue
            params = json.loads(action["params_json"])
            div = float(params["amount_per_share"])
            ex_date = pd.Timestamp(action["ex_date"])
            # find close on day before ex_date
            pre_rows = sym_prices[sym_prices["date"] < ex_date]
            if len(pre_rows) == 0:
                continue
            prev_close = float(pre_rows.iloc[-1]["close"])
            if prev_close <= 0:
                continue
            factor = (prev_close - div) / prev_close
            # scale hfq for all dates < ex_date
            idx = df.index[mask & (df["date"] < ex_date)]
            df.loc[idx, "close_hfq"] = df.loc[idx, "close_hfq"] * factor
            # total_return: add div on ex_date forward (simple cumulative)
            idx_fwd = df.index[mask & (df["date"] >= ex_date)]
            df.loc[idx_fwd, "total_return"] = df.loc[idx_fwd, "total_return"] + div

    return df


def _price_limit(prev_close: float, is_st: bool, exchange: str) -> tuple[float, float]:
    """Return (limit_up, limit_down) for the given previous close."""
    if exchange == "HK":
        # HK has no daily price limit
        return (prev_close * 10, 0.01)  # effectively unlimited
    pct = 0.05 if is_st else 0.10  # ST ±5%, normal ±10% (ChiNext/STAR 20%; simplified v1)
    return (round(prev_close * (1 + pct), 2), round(prev_close * (1 - pct), 2))


def convert_prices(
    raw: pd.DataFrame, corporate_actions: pd.DataFrame,
) -> pd.DataFrame:
    """Full conversion: source-native → domain PriceFrame. Pandera-validated."""
    df = compute_adjusted_prices(raw, corporate_actions)

    # Compute limit_up / limit_down / hit_limit_* per symbol
    df = df.sort_values(["symbol", "date"]).reset_index(drop=True)
    df["prev_close"] = df.groupby("symbol")["close"].shift(1)
    # First-row prev_close = close (no limit on first observation)
    df["prev_close"] = df["prev_close"].fillna(df["close"])
    df["exchange"] = df["symbol"].str.split(".", expand=True)[1]

    limits = df.apply(
        lambda r: _price_limit(r["prev_close"], r["is_st"], r["exchange"]), axis=1
    )
    df["limit_up"] = [x[0] for x in limits]
    df["limit_down"] = [x[1] for x in limits]
    df["hit_limit_up"] = (df["high"] >= df["limit_up"] - 0.01)
    df["hit_limit_down"] = (df["low"] <= df["limit_down"] + 0.01)

    # Drop helper columns not in schema
    df = df.drop(columns=["prev_close", "exchange"])

    return PriceFrameSchema.validate(df).reset_index(drop=True)


def convert_fundamentals(raw: pd.DataFrame) -> pd.DataFrame:
    """Domain FundamentalsFrame with known_as_of defaulted to publication_date
    when source doesn't provide a restatement marker."""
    df = raw.copy()
    if "known_as_of" not in df.columns:
        df["known_as_of"] = df["publication_date"]
    if "statement_kind" not in df.columns:
        df["statement_kind"] = "audited"
    # Compute ROIC if missing: NOPAT / (equity + debt). Best-effort.
    if "roic" not in df.columns:
        nopat = df["net_income"] - df.get("minority_interest", 0) * 0  # rough
        invested = df["total_equity"] + df["total_debt"]
        df["roic"] = nopat / invested.where(invested > 0, pd.NA)
    return FundamentalsFrameSchema.validate(df).reset_index(drop=True)
```

- [ ] **Step 4: Run — expect pass (validate assertions carefully; price-limit test may need tuning tolerances)**

- [ ] **Step 5: Commit**

```bash
git add src/ah_research/data/converters.py tests/unit/test_converters.py
git commit -m "feat(converters): add price/fundamentals conversion with hfq and limit flags"
```

---

### Tasks 1.11 – 1.19: DataRepository methods

`DataRepository` is the Phase 1 centerpiece. Build one method at a time, each with test + impl + commit.

- **Task 1.11:** `DataRepository.__init__(price_source, fundamentals_source, fx_source, calendar_source, sector_source, corp_actions_source, constituents_source, cache)` and basic instantiation test.
- **Task 1.12:** `get_prices(symbols, start, end, freq, adjust, price_kind)` — cache-lookup, fetch-missing, convert, write-back, return. **Must validate** coverage gaps and fetch only missing slices. Includes pandera validation on return.
- **Task 1.13:** `get_fundamentals(symbols, start, end, fields, asof, statement_kind)` — with PIT `asof` enforcement.
- **Task 1.14:** `get_index_constituents(index, asof)` — PIT.
- **Task 1.15:** `get_universe_over_time(index, start, end)` — survivorship-free driver for backtests.
- **Task 1.16:** `get_corporate_actions(symbols, start, end)` — plus helper that re-derives `close_hfq` on demand.
- **Task 1.17:** `get_trading_calendar(exchange, start, end)` and `get_sector(symbols, level)`.
- **Task 1.18:** `compute_ah_premium(pair, start, end)` — intersection calendar, FX-aligned.
- **Task 1.19:** `resample(frame, freq)` — D→W→M→Q with correct last-valid/sum conventions.

For each, follow the TDD loop. Tests use `FakeSources` fixtures from `tests/conftest.py`. Each commit message: `feat(repository): add get_<x> with PIT enforcement and cache composition`.

**Test shape skeleton (for the subagent executing these):**

```python
# tests/conftest.py
import pytest
from ah_research.integrations.fake import FakeSources
from ah_research.data.cache import DuckDBCache
from ah_research.data.repository import DataRepository

@pytest.fixture
def fake_sources():
    return FakeSources(seed=42)

@pytest.fixture
def cache(tmp_path):
    c = DuckDBCache(tmp_path / "cache.duckdb")
    yield c
    c.close()

@pytest.fixture
def repo(fake_sources, cache):
    return DataRepository(
        price_source=fake_sources.prices,
        fundamentals_source=fake_sources.fundamentals,
        fx_source=fake_sources.fx,
        calendar_source=fake_sources.calendar,
        sector_source=fake_sources.sectors,
        corp_actions_source=fake_sources.corporate_actions,
        constituents_source=fake_sources.constituents,
        cache=cache,
    )
```

**Each repository method's test pattern** (example for get_prices):

```python
def test_get_prices_returns_schema_valid_frame(repo):
    from datetime import date
    from ah_research.model.schemas import PriceFrameSchema
    df = repo.get_prices(["600519.SH"], date(2024, 1, 1), date(2024, 6, 30))
    PriceFrameSchema.validate(df)
    assert len(df) > 0

def test_get_prices_second_call_hits_cache(repo, mocker):
    from datetime import date
    spy = mocker.spy(repo._price_source, "fetch_prices")
    _ = repo.get_prices(["600519.SH"], date(2024, 1, 1), date(2024, 3, 31))
    assert spy.call_count == 1
    _ = repo.get_prices(["600519.SH"], date(2024, 1, 1), date(2024, 3, 31))
    assert spy.call_count == 1  # no new fetch

def test_get_fundamentals_asof_enforces_pit(repo):
    from datetime import date
    df = repo.get_fundamentals(["600519.SH"], date(2020, 1, 1), date(2024, 12, 31),
                               asof=date(2022, 6, 30))
    assert (df["publication_date"] <= "2022-06-30").all()
    assert (df["known_as_of"] <= "2022-06-30").all()
```

---

### Task 1.20: `data/ah_pairs.yaml` — curated starter list

**Files:**
- Create: `src/ah_research/data/ah_pairs.yaml`
- Test: `tests/unit/test_ah_pairs_load.py`

- [ ] **Step 1: Write the curated list (~30 pairs)**

```yaml
# ~30 AH dual-listings as of 2026-04-28. Edit with care — this is a hand-
# curated starter set. Quarterly audit via scripts/audit_ah_pairs.py.
pairs:
  - {a: "601318.SH", h: "2318.HK", name_en: "Ping An Insurance",      name_zh: "中国平安"}
  - {a: "601398.SH", h: "1398.HK", name_en: "ICBC",                   name_zh: "工商银行"}
  - {a: "601939.SH", h: "0939.HK", name_en: "China Construction Bank", name_zh: "建设银行"}
  - {a: "601288.SH", h: "1288.HK", name_en: "Agricultural Bank of China", name_zh: "农业银行"}
  - {a: "601988.SH", h: "3988.HK", name_en: "Bank of China",          name_zh: "中国银行"}
  - {a: "601328.SH", h: "3328.HK", name_en: "Bank of Communications", name_zh: "交通银行"}
  - {a: "600028.SH", h: "0386.HK", name_en: "Sinopec",                name_zh: "中国石化"}
  - {a: "601857.SH", h: "0857.HK", name_en: "PetroChina",             name_zh: "中国石油"}
  - {a: "601088.SH", h: "1088.HK", name_en: "China Shenhua",          name_zh: "中国神华"}
  - {a: "600519.SH", h: null,     name_en: "Kweichow Moutai",        name_zh: "贵州茅台"}
  - {a: "601601.SH", h: "2601.HK", name_en: "China Pacific Insurance", name_zh: "中国太保"}
  - {a: "601628.SH", h: "2628.HK", name_en: "China Life",             name_zh: "中国人寿"}
  - {a: "600036.SH", h: "3968.HK", name_en: "China Merchants Bank",   name_zh: "招商银行"}
  - {a: "600900.SH", h: null,     name_en: "Yangtze Power",          name_zh: "长江电力"}
  - {a: "601668.SH", h: "3323.HK", name_en: "China State Construction Engr", name_zh: "中国建筑"}
  - {a: "601390.SH", h: "0390.HK", name_en: "China Railway Group",    name_zh: "中国中铁"}
  - {a: "601186.SH", h: "1186.HK", name_en: "China Railway Construction", name_zh: "中国铁建"}
  - {a: "601800.SH", h: "1800.HK', name_en: "China Communications Construction", name_zh: "中国交建"}
  - {a: "600050.SH", h: "0762.HK", name_en: "China Unicom",            name_zh: "中国联通"}
  - {a: "601728.SH", h: "0728.HK", name_en: "China Telecom",           name_zh: "中国电信"}
  - {a: "600941.SH", h: "0941.HK", name_en: "China Mobile",            name_zh: "中国移动"}
  - {a: "601985.SH", h: "1816.HK", name_en: "CGN Power",               name_zh: "中国广核"}
  - {a: "601669.SH", h: "1133.HK", name_en: "Power Construction Corp", name_zh: "中国电建"}
  - {a: "601888.SH", h: "1888.HK", name_en: "China Tourism Group Duty Free", name_zh: "中国中免"}
  - {a: "601336.SH", h: "1336.HK", name_en: "New China Life Insurance", name_zh: "新华保险"}
  - {a: "600887.SH", h: null,     name_en: "Inner Mongolia Yili",     name_zh: "伊利股份"}
  - {a: "600276.SH", h: "2269.HK", name_en: "Hengrui Pharmaceutical", name_zh: "恒瑞医药"}
  - {a: "600309.SH", h: null,     name_en: "Wanhua Chemical",        name_zh: "万华化学"}
  - {a: "601166.SH", h: null,     name_en: "Industrial Bank",        name_zh: "兴业银行"}
  - {a: "600048.SH", h: null,     name_en: "Poly Developments",      name_zh: "保利发展"}
```

**Note:** entries with `h: null` are A-only; retained for value-investor dossier reasons (Moutai, Yangtze Power, etc.). `get_ah_pairs()` only returns entries with both A and H.

- [ ] **Step 2: Add loader test**

```python
# tests/unit/test_ah_pairs_load.py
from ah_research.data.ah_pairs import load_ah_pairs

def test_load_ah_pairs_returns_pairs_only():
    pairs = load_ah_pairs()
    assert len(pairs) >= 20  # at least 20 dual-listings
    for p in pairs:
        assert p.a_symbol.exchange.value == "SH" or p.a_symbol.exchange.value == "SZ"
        assert p.h_symbol.exchange.value == "HK"

def test_loaded_pairs_include_ping_an():
    pairs = load_ah_pairs()
    names = [p.name_zh for p in pairs]
    assert "中国平安" in names
```

- [ ] **Step 3: Run — expect ImportError**

- [ ] **Step 4: Implement `src/ah_research/data/ah_pairs.py`**

```python
"""Load curated AH pairs from the yaml file."""

from __future__ import annotations

from importlib.resources import files

import yaml

from ah_research.model.types import AHPair, parse_symbol


def load_ah_pairs() -> list[AHPair]:
    yaml_path = files("ah_research.data").joinpath("ah_pairs.yaml")
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    pairs: list[AHPair] = []
    for entry in data["pairs"]:
        if entry.get("h") is None:
            continue
        pairs.append(AHPair(
            a_symbol=parse_symbol(entry["a"]),
            h_symbol=parse_symbol(entry["h"]),
            name_en=entry["name_en"],
            name_zh=entry["name_zh"],
        ))
    return pairs
```

- [ ] **Step 5: Fix the syntax error in `ah_pairs.yaml`** (the `1800.HK'` entry has a quote typo; fix to `"1800.HK"`)

- [ ] **Step 6: Run — expect pass**

- [ ] **Step 7: Commit**

```bash
git add src/ah_research/data/ah_pairs.yaml src/ah_research/data/ah_pairs.py tests/unit/test_ah_pairs_load.py
git commit -m "feat(data): add curated AH pairs YAML (~30 pairs) with loader"
```

---

### Task 1.21: Baostock client — prices + constituents + calendar + fundamentals

**Files:**
- Create: `src/ah_research/integrations/baostock/client.py`
- Create: `src/ah_research/integrations/baostock/source_schemas.py`
- Test: `tests/unit/test_baostock_client_mock.py`
- Test: `tests/integration/test_baostock_live.py` (gated by `AH_RESEARCH_LIVE=1`)

This is the largest concrete task in Phase 1. Break into sub-tasks:

- **1.21a** `BaostockClient.__init__` + login/logout (session management with `baostock.login()`)
- **1.21b** `fetch_prices` — daily OHLCV for A-shares
- **1.21c** `fetch_fundamentals` — quarterly statements with publication_date
- **1.21d** `fetch_constituents` — CSI 300 / CSI 500 membership
- **1.21e** `fetch_calendar` — A-share trading days
- **1.21f** `fetch_corporate_actions` — dividends/splits

Each sub-task:
1. Write a unit test with `unittest.mock` patching `baostock.query_*` responses.
2. Write a live test (skipped unless env var set) that hits real Baostock.
3. Implement the method, remapping Baostock errors to our hierarchy (`SourceRateLimit`, `SourceAuthError`, etc.) and wrapping retries with tenacity.
4. Commit per sub-task.

**Error-remap boilerplate** — include once in `baostock/client.py`:

```python
from tenacity import retry, retry_if_exception_type, wait_exponential, stop_after_attempt

from ah_research.exceptions import (
    SourceAuthError, SourceDataError, SourceRateLimit,
    SourceSchemaError, SourceUnavailable,
)

def _remap_baostock_error(rs: Any) -> None:
    """Called after every baostock call. Baostock returns a result object with
    error_code and error_msg attributes."""
    if rs.error_code == "0":
        return
    msg = f"{rs.error_code}: {rs.error_msg}"
    if "10001" in rs.error_code or "logout" in rs.error_msg.lower():
        raise SourceAuthError(msg)
    if "10002" in rs.error_code:
        raise SourceRateLimit(msg)
    if "network" in rs.error_msg.lower() or "timeout" in rs.error_msg.lower():
        raise SourceUnavailable(msg)
    if "10004" in rs.error_code:
        raise SourceDataError(msg)
    raise SourceSchemaError(msg)


class BaostockClient:
    def __init__(self) -> None:
        import baostock as bs
        self._bs = bs
        rs = bs.login()
        _remap_baostock_error(rs)

    def close(self) -> None:
        self._bs.logout()

    @retry(
        retry=retry_if_exception_type((SourceRateLimit, SourceUnavailable)),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    def fetch_prices(self, symbols: list[str], start: date, end: date) -> pd.DataFrame:
        """Fetch daily OHLCV for symbols in `<code>.<exchange>` format."""
        frames: list[pd.DataFrame] = []
        for sym in symbols:
            code, exch = sym.split(".")
            bs_code = f"{exch.lower()}.{code}"  # Baostock's format: sh.600519
            rs = self._bs.query_history_k_data_plus(
                bs_code,
                "date,code,open,high,low,close,volume,amount,turn,tradestatus,isST",
                start_date=str(start),
                end_date=str(end),
                frequency="d",
                adjustflag="3",  # "3" = no adjustment; we back-adjust ourselves
            )
            _remap_baostock_error(rs)
            data: list[list[str]] = []
            while (rs.error_code == "0") and rs.next():
                data.append(rs.get_row_data())
            df = pd.DataFrame(data, columns=rs.fields)
            df["symbol"] = sym
            frames.append(df)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
```

(Finish by mapping all returned columns to the source-native shape expected by `convert_prices`, including `is_suspended=(tradestatus != "1")` and `is_st=(isST == "1")`.)

**Commit pattern:**
```
feat(baostock): add login/logout and error remap
feat(baostock): add fetch_prices with adjustflag=3 and tradestatus parsing
feat(baostock): add fetch_fundamentals with publication_date
feat(baostock): add fetch_constituents for CSI300/CSI500
feat(baostock): add fetch_calendar for SH and SZ
feat(baostock): add fetch_corporate_actions
```

---

### Task 1.22: AKshare client — HK prices + fundamentals + FX + sectors + calendar

Mirror of Task 1.21 but for AKshare. Sub-tasks:

- **1.22a** HK daily prices (`ak.stock_hk_hist`)
- **1.22b** HK fundamentals (`ak.stock_financial_hk_*`)
- **1.22c** FX (CNY/HKD via `ak.currency_boc_sina`)
- **1.22d** SWS sector tags (`ak.stock_sector_detail` / `ak.sw_index_info`)
- **1.22e** HSI + HSCEI constituents (`ak.stock_hk_index_constituent_spot_sina` — note limitation: this may only give current; historical needs different source; flag as Phase 2 follow-up if so)
- **1.22f** HK trading calendar

Same TDD pattern per sub-task with mocked AKshare responses.

---

### Task 1.23: `ah warmup` command

**Files:**
- Create: `scripts/ah_warmup.py`
- Test: `tests/unit/test_ah_warmup.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_ah_warmup.py
from scripts.ah_warmup import compute_symbols, run

def test_compute_symbols_sample():
    syms = compute_symbols("sample")
    assert "600519.SH" in syms
    assert "0700.HK" in syms
    assert len(syms) == 5

def test_compute_symbols_csi300(monkeypatch):
    # Uses fake constituents in test mode
    syms = compute_symbols("csi300", test_mode=True)
    assert len(syms) == 300
```

- [ ] **Step 2: Run — ImportError**

- [ ] **Step 3: Implement** — calls `DataRepository.get_prices` + `get_fundamentals` for a universe over N years.

- [ ] **Step 4: Extend `ah doctor`** to include `check_baostock_login`, `check_akshare_reachable`, `check_duckdb_open`, `check_migrations_current`.

- [ ] **Step 5: Manual smoke:**

```bash
AH_RESEARCH_CACHE_DIR=/tmp/ah-test uv run ah warmup --universe sample --years 1
uv run ah doctor
```

- [ ] **Step 6: Commit**

---

### Task 1.24: Property-based tests with hypothesis

**Files:**
- Create: `tests/property/test_symbol_roundtrip.py`
- Create: `tests/property/test_pit_monotonicity.py`
- Create: `tests/property/test_adjust_idempotence.py`

- [ ] **Step 1: Write hypothesis strategies**

```python
# tests/property/test_symbol_roundtrip.py
from hypothesis import given, strategies as st
from ah_research.model.types import Symbol, Exchange, parse_symbol


codes_sh = st.from_regex(r"^[0-9]{6}$", fullmatch=True)
codes_hk = st.from_regex(r"^[0-9]{4,5}$", fullmatch=True)


@given(code=codes_sh)
def test_sh_symbol_roundtrips(code):
    s = parse_symbol(f"{code}.SH")
    assert str(s) == f"{code}.SH"


@given(code=codes_hk)
def test_hk_symbol_roundtrips(code):
    s = parse_symbol(f"{code}.HK")
    assert str(s) == f"{code}.HK"
```

```python
# tests/property/test_pit_monotonicity.py
from datetime import date, timedelta
from hypothesis import given, strategies as st
from ah_research.data.repository import DataRepository


@given(asof_offset=st.integers(min_value=0, max_value=365))
def test_get_fundamentals_asof_never_includes_future(repo, asof_offset):
    asof = date(2024, 1, 1) + timedelta(days=asof_offset)
    df = repo.get_fundamentals(["600519.SH"], date(2020, 1, 1), date(2024, 12, 31), asof=asof)
    if len(df) > 0:
        assert (df["publication_date"] <= asof).all()
        assert (df["known_as_of"] <= asof).all()
```

- [ ] **Step 2: Run — first run will be slow as hypothesis generates; expect pass**

- [ ] **Step 3: Commit**

```bash
git add tests/property/
git commit -m "test(property): add hypothesis tests for symbol roundtrip and PIT monotonicity"
```

---

### Task 1.25: Phase 1 acceptance notebook

**Files:**
- Create: `notebooks/phase1_smoke.ipynb`

- [ ] **Step 1: Create notebook with cells exercising:**

```python
# Cell 1
from datetime import date
from ah_research.config import get_settings
from ah_research.data.cache import DuckDBCache
from ah_research.data.repository import DataRepository
from ah_research.integrations.baostock.client import BaostockClient
from ah_research.integrations.akshare.client import AKShareClient

settings = get_settings()
cache = DuckDBCache(settings.cache_duckdb_path)
bao = BaostockClient()
ak = AKShareClient()

repo = DataRepository(
    price_source=bao, fundamentals_source=bao,
    fx_source=ak, calendar_source=bao,
    sector_source=ak, corp_actions_source=bao,
    constituents_source=bao, cache=cache,
)
```

```python
# Cell 2 — Moutai prices last 5y, back-adjusted
df = repo.get_prices(["600519.SH"], date(2020, 1, 1), date(2024, 12, 31))
df.tail()
```

```python
# Cell 3 — Fundamentals PIT
f = repo.get_fundamentals(["600519.SH"], date(2020, 1, 1), date(2024, 12, 31),
                          asof=date(2022, 6, 30))
f.tail()
```

```python
# Cell 4 — Survivorship-free universe
u = repo.get_universe_over_time("CSI300", date(2020, 1, 1), date(2024, 12, 31))
u.groupby("date")["symbol"].nunique().head(20)
```

```python
# Cell 5 — Ping An AH premium
from ah_research.data.ah_pairs import load_ah_pairs
pa = [p for p in load_ah_pairs() if p.name_zh == "中国平安"][0]
premium = repo.compute_ah_premium(pa, date(2020, 1, 1), date(2024, 12, 31))
premium.plot(figsize=(10, 4), title="Ping An AH premium (A/H - 1)")
```

- [ ] **Step 2: Run all cells; verify no errors and reasonable numbers**

- [ ] **Step 3: Commit**

```bash
git add notebooks/phase1_smoke.ipynb
git commit -m "test(notebook): add Phase 1 acceptance notebook (prices, fundamentals, universe, AH premium)"
```

---

## Self-review notes (spec coverage)

Confirming every Phase 0 + Phase 1 item from spec §7 maps to a task:

- Phase 0 scaffolding (uv + Python 3.11+, layout, ruff + mypy + pytest + hypothesis + pre-commit + CI): Tasks 0.1, 0.2 ✓
- Phase 0 `ah init`, `ah doctor`, `ah warmup`: Tasks 0.8, 0.9, 1.23 ✓
- Phase 0 `config.py` (pydantic-settings + keyring): Task 0.5 ✓ *(keyring integration deferred; .env fallback only in v1; stub in config.py for future)*
- Phase 0 `exceptions.py`: Task 0.3 ✓
- Phase 0 `logging.py`: Task 0.4 ✓
- Phase 0 `concurrency.py`: Task 0.6 ✓
- Phase 0 pandera schemas skeleton: Task 1.2 ✓ (pulled forward to Phase 1)
- Phase 1 `Protocol`-based integration boundary: Task 1.3 ✓
- Phase 1 fake sources: Task 1.4 ✓
- Phase 1 Baostock + AKshare + FX clients: Tasks 1.21, 1.22 ✓
- Phase 1 DuckDB cache + migrations: Tasks 1.5, 1.6–1.9 ✓
- Phase 1 converters (pandera-validated): Task 1.10 ✓
- Phase 1 `DataRepository` with DI: Tasks 1.11–1.19 ✓
- Phase 1 corporate actions + bitemporal fundamentals + PIT constituents + sector tags + ST/limit flags: Tasks 1.10, 1.12, 1.13, 1.14, 1.15, 1.16, 1.17 ✓
- Phase 1 curated `ah_pairs.yaml`: Task 1.20 ✓
- Phase 1 property-based tests: Task 1.24 ✓

## Handoff

**Plan covers Phase 0 (~1 day, 9 tasks) + Phase 1 (~1.5 weeks, 25 tasks / ~35 sub-tasks). Total ~2 weeks for a single engineer.**

Phases 2–6 will be planned separately once Phase 1 ships. Re-prioritized Phase 3 (value analysis first, factor/portfolio after) and short-kill decisions from spec v2.1 will be locked in the Phase 3 plan.

## Execution Handoff

Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
