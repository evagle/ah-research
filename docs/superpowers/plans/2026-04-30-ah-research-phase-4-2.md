# Phase 4.2 — Filings + Profile Repositories Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development to implement task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Build `FilingsRepository` + `ProfileRepository` + `Filing`/`Profile` dataclasses, wire CLI subcommands `ah filings` and `ah profile`, ship an acceptance notebook.

**Architecture:** New `src/ah_research/filings/` package (two repos + shared types), two new CLI scripts registered into the main Typer app.

**Tech Stack:** Python 3.11+, Typer (existing), pytest + hypothesis (existing), nbclient for notebook tests (existing). **No new runtime dependencies.**

**Spec:** `docs/superpowers/specs/2026-04-30-ah-research-phase-4-2-filings-design.md`
**Branch:** `feat/phase-4.2` (already checked out, off `origin/main`)

---

## Naming contracts

- `Filing`, `Profile` — frozen dataclasses
- `FilingsRepository`, `ProfileRepository` — service classes
- `FilingKind` = `Literal["annual", "ipo", "research"]`
- Module paths: `ah_research.filings.types`, `ah_research.filings.filings_repository`, `ah_research.filings.profile_repository`
- CLI sub-apps: `filings_app`, `profile_app` in `src/ah_research/scripts/ah_filings.py` / `ah_profile.py`
- Repository defaults: `FilingsRepository(root=Path("data/filings"))`, `ProfileRepository(root=Path("profiles"))`
- Filename patterns:
  - Annual: `年报-<YYYY>.md` where YYYY is 4 digits
  - IPO: `招股说明书.md` (exact match)
  - Research: anything ending `.md` under `<ticker>/research/`; try to parse `<brokerage>-<title>-<YYYYMMDD>.md` but don't require
  - Profile: `<symbol>-<YYYY-MM-DD>.md` excluding any `-evaluation.md` suffix

---

## Task 1: `Filing` + `Profile` dataclasses + tests

**Files:**
- Create: `src/ah_research/filings/__init__.py`
- Create: `src/ah_research/filings/types.py`
- Create: `tests/unit/filings/__init__.py`
- Create: `tests/unit/filings/test_types.py`

- [ ] **Step 1.1 — scaffold**
```bash
mkdir -p src/ah_research/filings tests/unit/filings tests/unit/scripts tests/integration tests/fixtures/phase4_2/filings tests/fixtures/phase4_2/profiles
touch src/ah_research/filings/__init__.py tests/unit/filings/__init__.py
```

- [ ] **Step 1.2 — failing tests** in `tests/unit/filings/test_types.py`:
```python
from datetime import date
from pathlib import Path

import pytest

from ah_research.filings.types import Filing, Profile


def test_filing_is_frozen():
    f = Filing(symbol="600519.SH", kind="annual", path=Path("x.md"), text="body", year=2024)
    with pytest.raises(Exception):
        f.symbol = "other"


def test_filing_defaults():
    f = Filing(symbol="600519.SH", kind="ipo", path=Path("x.md"), text="body")
    assert f.year is None
    assert f.title is None
    assert f.date is None


def test_profile_frozen_with_sections():
    p = Profile(
        symbol="600519.SH",
        date=date(2026, 4, 28),
        path=Path("x.md"),
        text="# Header\n\n## Sec 1\nbody",
        sections={"Sec 1": "body"},
    )
    assert p.sections["Sec 1"] == "body"
    with pytest.raises(Exception):
        p.text = "other"
```

- [ ] **Step 1.3 — implement** `src/ah_research/filings/types.py`:
```python
"""Frozen dataclasses for filings and profiles."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date as _date
from pathlib import Path
from typing import Literal

FilingKind = Literal["annual", "ipo", "research"]


@dataclass(frozen=True)
class Filing:
    symbol: str
    kind: FilingKind
    path: Path
    text: str
    year: int | None = None
    title: str | None = None
    date: _date | None = None


@dataclass(frozen=True)
class Profile:
    symbol: str
    date: _date
    path: Path
    text: str
    sections: Mapping[str, str] = field(default_factory=dict)
```

- [ ] **Step 1.4 — also export from package**: write `src/ah_research/filings/__init__.py`:
```python
"""ah_research.filings — Phase 4.2 markdown artifact repositories."""

from ah_research.filings.types import Filing, FilingKind, Profile

__all__ = ["Filing", "FilingKind", "Profile"]
```

- [ ] **Step 1.5 — run**
```bash
uv run pytest tests/unit/filings/test_types.py -v
```
Expected: 3 passes.

- [ ] **Step 1.6 — commit**
```bash
git add src/ah_research/filings tests/unit/filings
git commit -m "feat(phase-4.2): Filing + Profile dataclasses"
```

---

## Task 2: `FilingsRepository` + tests + fixtures

**Files:**
- Create: `src/ah_research/filings/filings_repository.py`
- Create: `tests/unit/filings/test_filings_repository.py`
- Create fixtures: `tests/fixtures/phase4_2/filings/600000.SH/年报-2023.md`, `年报-2024.md`, `招股说明书.md`, `research/broker-a-report-20240315.md`; `tests/fixtures/phase4_2/filings/000001.SZ/年报-2024.md`

- [ ] **Step 2.1 — write fixtures**
```bash
mkdir -p tests/fixtures/phase4_2/filings/600000.SH/research tests/fixtures/phase4_2/filings/000001.SZ

printf '# Annual 2023\nbody' > tests/fixtures/phase4_2/filings/600000.SH/年报-2023.md
printf '# Annual 2024\nbody' > tests/fixtures/phase4_2/filings/600000.SH/年报-2024.md
printf '# IPO\nbody'         > tests/fixtures/phase4_2/filings/600000.SH/招股说明书.md
printf '# Research\nbody'    > tests/fixtures/phase4_2/filings/600000.SH/research/broker-a-report-20240315.md
printf '# Annual 2024\nbody' > tests/fixtures/phase4_2/filings/000001.SZ/年报-2024.md
```

- [ ] **Step 2.2 — failing tests** `tests/unit/filings/test_filings_repository.py`:
```python
from pathlib import Path

import pytest

from ah_research.filings.filings_repository import FilingsRepository
from ah_research.model.types import parse_symbol
from ah_research.portfolio.optimizer.errors import ValidationError  # re-use? no — use stdlib ValueError

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "phase4_2" / "filings"


@pytest.fixture
def repo() -> FilingsRepository:
    return FilingsRepository(root=FIXTURES)


def test_list_symbols(repo: FilingsRepository):
    syms = repo.list_symbols()
    assert set(syms) == {"600000.SH", "000001.SZ"}


def test_list_filings_contains_all_kinds(repo: FilingsRepository):
    filings = repo.list_filings("600000.SH")
    kinds = [f.kind for f in filings]
    assert kinds.count("annual") == 2
    assert kinds.count("ipo") == 1
    assert kinds.count("research") == 1


def test_list_filings_empty_for_unknown_symbol(repo: FilingsRepository):
    assert repo.list_filings("999999.SH") == []


def test_get_annual_returns_filing(repo: FilingsRepository):
    f = repo.get_annual("600000.SH", 2024)
    assert f.year == 2024
    assert f.text.startswith("# Annual 2024")


def test_get_annual_raises_when_year_missing(repo: FilingsRepository):
    with pytest.raises(FileNotFoundError):
        repo.get_annual("600000.SH", 1999)


def test_latest_annual_returns_highest_year(repo: FilingsRepository):
    f = repo.latest_annual("600000.SH")
    assert f is not None
    assert f.year == 2024


def test_latest_annual_none_for_empty(repo: FilingsRepository):
    assert repo.latest_annual("999999.SH") is None


def test_get_ipo_returns_ipo(repo: FilingsRepository):
    f = repo.get_ipo("600000.SH")
    assert f is not None
    assert f.kind == "ipo"


def test_get_ipo_none_when_missing(repo: FilingsRepository):
    assert repo.get_ipo("000001.SZ") is None


def test_get_research_returns_list(repo: FilingsRepository):
    rs = repo.get_research("600000.SH")
    assert len(rs) == 1
    assert rs[0].title is not None or rs[0].path.name.startswith("broker-a")


def test_get_research_empty_when_dir_missing(repo: FilingsRepository):
    assert repo.get_research("000001.SZ") == []


def test_invalid_symbol_raises(repo: FilingsRepository):
    with pytest.raises(Exception):  # ValueError from parse_symbol
        repo.list_filings("not-a-symbol")
```

- [ ] **Step 2.3 — implement** `src/ah_research/filings/filings_repository.py`:
```python
"""FilingsRepository — indexes data/filings/<ticker>/*.md and research subdir."""

from __future__ import annotations

import re
from datetime import date as _date
from pathlib import Path

from ah_research.filings.types import Filing, FilingKind
from ah_research.model.types import parse_symbol

_ANNUAL_RE = re.compile(r"^年报-(\d{4})\.md$")
_IPO_NAME = "招股说明书.md"
_RESEARCH_DATE_RE = re.compile(r"(\d{8})\.md$")


class FilingsRepository:
    def __init__(self, root: Path = Path("data/filings")) -> None:
        self.root = Path(root)

    def list_symbols(self) -> list[str]:
        if not self.root.exists():
            return []
        return sorted(
            p.name for p in self.root.iterdir()
            if p.is_dir() and not p.name.startswith("_") and not p.name.startswith(".")
        )

    def list_filings(self, symbol: str) -> list[Filing]:
        parse_symbol(symbol)  # validate format
        sym_dir = self.root / symbol
        if not sym_dir.exists():
            return []
        filings: list[Filing] = []
        filings.extend(self._annuals(symbol, sym_dir))
        ipo = self._ipo(symbol, sym_dir)
        if ipo is not None:
            filings.append(ipo)
        filings.extend(self._researches(symbol, sym_dir))
        return filings

    def get_annual(self, symbol: str, year: int) -> Filing:
        parse_symbol(symbol)
        path = self.root / symbol / f"年报-{year}.md"
        if not path.exists():
            raise FileNotFoundError(f"No annual report for {symbol} year={year} at {path}")
        return Filing(symbol=symbol, kind="annual", path=path, text=path.read_text(encoding="utf-8"), year=year)

    def latest_annual(self, symbol: str) -> Filing | None:
        parse_symbol(symbol)
        sym_dir = self.root / symbol
        if not sym_dir.exists():
            return None
        years: list[int] = []
        for p in sym_dir.iterdir():
            m = _ANNUAL_RE.match(p.name)
            if m:
                years.append(int(m.group(1)))
        if not years:
            return None
        return self.get_annual(symbol, max(years))

    def get_ipo(self, symbol: str) -> Filing | None:
        parse_symbol(symbol)
        path = self.root / symbol / _IPO_NAME
        if not path.exists():
            return None
        return Filing(symbol=symbol, kind="ipo", path=path, text=path.read_text(encoding="utf-8"))

    def get_research(self, symbol: str) -> list[Filing]:
        parse_symbol(symbol)
        rdir = self.root / symbol / "research"
        if not rdir.exists():
            return []
        out: list[Filing] = []
        for p in sorted(rdir.glob("*.md"), reverse=True):
            out.append(Filing(
                symbol=symbol, kind="research", path=p,
                text=p.read_text(encoding="utf-8"),
                title=p.stem,
                date=_extract_date(p.name),
            ))
        return sorted(out, key=lambda f: (f.date or _date.min), reverse=True)

    # -- internals -----------------------------------------------------------

    def _annuals(self, symbol: str, sym_dir: Path) -> list[Filing]:
        out: list[Filing] = []
        for p in sorted(sym_dir.iterdir()):
            m = _ANNUAL_RE.match(p.name)
            if m:
                year = int(m.group(1))
                out.append(Filing(
                    symbol=symbol, kind="annual", path=p,
                    text=p.read_text(encoding="utf-8"),
                    year=year,
                ))
        return sorted(out, key=lambda f: f.year or 0, reverse=True)

    def _ipo(self, symbol: str, sym_dir: Path) -> Filing | None:
        path = sym_dir / _IPO_NAME
        if not path.exists():
            return None
        return Filing(symbol=symbol, kind="ipo", path=path, text=path.read_text(encoding="utf-8"))

    def _researches(self, symbol: str, sym_dir: Path) -> list[Filing]:
        rdir = sym_dir / "research"
        if not rdir.exists():
            return []
        out: list[Filing] = []
        for p in sorted(rdir.glob("*.md")):
            out.append(Filing(
                symbol=symbol, kind="research", path=p,
                text=p.read_text(encoding="utf-8"),
                title=p.stem,
                date=_extract_date(p.name),
            ))
        return out


def _extract_date(name: str) -> _date | None:
    m = _RESEARCH_DATE_RE.search(name)
    if not m:
        return None
    s = m.group(1)
    try:
        return _date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    except ValueError:
        return None
```

- [ ] **Step 2.4 — add to package exports**. Update `src/ah_research/filings/__init__.py`:
```python
"""ah_research.filings — Phase 4.2 markdown artifact repositories."""

from ah_research.filings.filings_repository import FilingsRepository
from ah_research.filings.types import Filing, FilingKind, Profile

__all__ = ["Filing", "FilingKind", "FilingsRepository", "Profile"]
```

- [ ] **Step 2.5 — run & fix** until green:
```bash
uv run pytest tests/unit/filings/test_filings_repository.py -v
```
Expected: 11 passes.

- [ ] **Step 2.6 — commit**
```bash
git add src/ah_research/filings tests/unit/filings tests/fixtures/phase4_2/filings
git commit -m "feat(phase-4.2): FilingsRepository (annual + ipo + research)"
```

---

## Task 3: `ProfileRepository` + section parser + tests + fixtures

**Files:**
- Create: `src/ah_research/filings/profile_repository.py`
- Create: `tests/unit/filings/test_profile_repository.py`
- Create fixtures: `tests/fixtures/phase4_2/profiles/600000.SH-2026-04-28.md`, `600000.SH-2026-04-28-evaluation.md`, `000001.SZ-2026-03-15.md`

- [ ] **Step 3.1 — fixtures**:
```bash
mkdir -p tests/fixtures/phase4_2/profiles

cat > tests/fixtures/phase4_2/profiles/600000.SH-2026-04-28.md <<'EOF'
# 600000.SH Profile

## §1 能力圈
圈内判断

## §2 护城河
护城河描述

### §2.1 子章节
子内容

## §3 管理层
管理层评估
EOF

cat > tests/fixtures/phase4_2/profiles/600000.SH-2026-04-28-evaluation.md <<'EOF'
# Eval (should be skipped)
body
EOF

cat > tests/fixtures/phase4_2/profiles/000001.SZ-2026-03-15.md <<'EOF'
# 000001.SZ Profile

no sub-sections — just header
EOF
```

- [ ] **Step 3.2 — failing tests** `tests/unit/filings/test_profile_repository.py`:
```python
from datetime import date
from pathlib import Path

import pytest

from ah_research.filings.profile_repository import ProfileRepository, parse_sections

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "phase4_2" / "profiles"


@pytest.fixture
def repo() -> ProfileRepository:
    return ProfileRepository(root=FIXTURES)


def test_list_symbols_excludes_evaluation(repo: ProfileRepository):
    syms = repo.list_symbols()
    assert set(syms) == {"600000.SH", "000001.SZ"}


def test_list_profiles_all(repo: ProfileRepository):
    assert len(repo.list_profiles()) == 2


def test_list_profiles_filtered(repo: ProfileRepository):
    assert len(repo.list_profiles("600000.SH")) == 1


def test_latest_returns_profile(repo: ProfileRepository):
    p = repo.latest("600000.SH")
    assert p is not None
    assert p.date == date(2026, 4, 28)


def test_get_raises_when_missing(repo: ProfileRepository):
    with pytest.raises(FileNotFoundError):
        repo.get("600000.SH", date(1999, 1, 1))


def test_sections_parsed(repo: ProfileRepository):
    p = repo.latest("600000.SH")
    assert p is not None
    assert "§1 能力圈" in p.sections
    assert "§2 护城河" in p.sections
    assert "§2 护城河 / §2.1 子章节" in p.sections
    assert "§3 管理层" in p.sections


def test_sections_preserve_body(repo: ProfileRepository):
    p = repo.latest("600000.SH")
    assert p is not None
    assert "圈内判断" in p.sections["§1 能力圈"]


def test_parse_sections_empty_when_no_h2():
    md = "# Only H1\n\nbody without sections"
    assert parse_sections(md) == {}


def test_parse_sections_chinese_headers():
    md = "## §A 标题\n体\n## §B 另一个\n内"
    sections = parse_sections(md)
    assert sections["§A 标题"].strip() == "体"
    assert sections["§B 另一个"].strip() == "内"


def test_evaluation_file_excluded(repo: ProfileRepository):
    for p in repo.list_profiles("600000.SH"):
        assert "evaluation" not in p.path.name
```

- [ ] **Step 3.3 — implement** `src/ah_research/filings/profile_repository.py`:
```python
"""ProfileRepository — indexes profiles/<ticker>-<date>.md, skipping -evaluation.md."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date as _date
from pathlib import Path

from ah_research.filings.types import Profile
from ah_research.model.types import parse_symbol

_PROFILE_RE = re.compile(r"^(?P<symbol>[0-9]{4,6}\.(?:SH|SZ|HK))-(?P<date>\d{4}-\d{2}-\d{2})\.md$")
_H2_RE = re.compile(r"^##\s+(.+?)\s*$", flags=re.MULTILINE)
_H3_RE = re.compile(r"^###\s+(.+?)\s*$", flags=re.MULTILINE)


class ProfileRepository:
    def __init__(self, root: Path = Path("profiles")) -> None:
        self.root = Path(root)

    def list_symbols(self) -> list[str]:
        return sorted({p.symbol for p in self.list_profiles()})

    def list_profiles(self, symbol: str | None = None) -> list[Profile]:
        if symbol is not None:
            parse_symbol(symbol)
        if not self.root.exists():
            return []
        out: list[Profile] = []
        for p in sorted(self.root.glob("*.md")):
            if p.name.endswith("-evaluation.md"):
                continue
            m = _PROFILE_RE.match(p.name)
            if not m:
                continue
            sym = m.group("symbol")
            if symbol is not None and sym != symbol:
                continue
            y, mo, d = map(int, m.group("date").split("-"))
            text = p.read_text(encoding="utf-8")
            out.append(Profile(
                symbol=sym,
                date=_date(y, mo, d),
                path=p,
                text=text,
                sections=parse_sections(text),
            ))
        return sorted(out, key=lambda pr: (pr.symbol, pr.date), reverse=True)

    def latest(self, symbol: str) -> Profile | None:
        profiles = self.list_profiles(symbol)
        return profiles[0] if profiles else None

    def get(self, symbol: str, date: _date) -> Profile:
        parse_symbol(symbol)
        path = self.root / f"{symbol}-{date.isoformat()}.md"
        if not path.exists():
            raise FileNotFoundError(f"No profile for {symbol} on {date}")
        text = path.read_text(encoding="utf-8")
        return Profile(
            symbol=symbol, date=date, path=path, text=text,
            sections=parse_sections(text),
        )


def parse_sections(md: str) -> Mapping[str, str]:
    """Parse markdown into section dict.

    - H2 headers (`^## `) are top-level keys.
    - H3 headers (`^### `) within a section are keyed as `"<parent> / <sub>"`.
    - Values are the body up to the next same-or-higher-level header.
    """
    sections: dict[str, str] = {}
    lines = md.splitlines()
    current_h2: str | None = None
    current_h2_body: list[str] = []
    current_h3: str | None = None
    current_h3_body: list[str] = []

    def flush_h3() -> None:
        nonlocal current_h3, current_h3_body
        if current_h3 is not None and current_h2 is not None:
            key = f"{current_h2} / {current_h3}"
            sections[key] = "\n".join(current_h3_body).strip()
        current_h3 = None
        current_h3_body = []

    def flush_h2() -> None:
        nonlocal current_h2, current_h2_body
        flush_h3()
        if current_h2 is not None:
            # only use body lines before any h3
            sections[current_h2] = "\n".join(current_h2_body).strip()
        current_h2 = None
        current_h2_body = []

    for line in lines:
        if _H2_RE.match(line):
            flush_h2()
            current_h2 = _H2_RE.match(line).group(1)  # type: ignore[union-attr]
        elif _H3_RE.match(line) and current_h2 is not None:
            # Before entering the h3, the h2 body is what we've accumulated so far.
            if current_h3 is None and current_h2_body:
                sections[current_h2] = "\n".join(current_h2_body).strip()
                current_h2_body = []  # don't double-count
            flush_h3()
            current_h3 = _H3_RE.match(line).group(1)  # type: ignore[union-attr]
        else:
            if current_h3 is not None:
                current_h3_body.append(line)
            elif current_h2 is not None:
                current_h2_body.append(line)
    flush_h2()
    return sections
```

- [ ] **Step 3.4 — update package `__init__.py`** to export `ProfileRepository`:
```python
from ah_research.filings.profile_repository import ProfileRepository

__all__ = ["Filing", "FilingKind", "FilingsRepository", "Profile", "ProfileRepository"]
```

- [ ] **Step 3.5 — run**:
```bash
uv run pytest tests/unit/filings/test_profile_repository.py -v
```
Expected: 10 passes.

- [ ] **Step 3.6 — commit**
```bash
git add src/ah_research/filings tests/unit/filings/test_profile_repository.py tests/fixtures/phase4_2/profiles
git commit -m "feat(phase-4.2): ProfileRepository with markdown section parser"
```

---

## Task 4: CLI `ah filings` + `ah profile` subcommands

**Files:**
- Create: `src/ah_research/scripts/ah_filings.py`
- Create: `src/ah_research/scripts/ah_profile.py`
- Modify: `src/ah_research/cli.py` (register both sub-apps)
- Create: `tests/unit/scripts/__init__.py`, `tests/unit/scripts/test_cli_filings.py`, `tests/unit/scripts/test_cli_profile.py`

- [ ] **Step 4.1 — tests** (fixtures reused from Tasks 2, 3).
Create `tests/unit/scripts/__init__.py` (empty).
Create `tests/unit/scripts/test_cli_filings.py`:
```python
from pathlib import Path

from typer.testing import CliRunner

from ah_research.scripts.ah_filings import filings_app

FIXTURES_ROOT = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "phase4_2" / "filings"
runner = CliRunner()


def test_list_all():
    result = runner.invoke(filings_app, ["list", "--root", str(FIXTURES_ROOT)])
    assert result.exit_code == 0, result.output
    assert "600000.SH" in result.output
    assert "000001.SZ" in result.output


def test_list_for_symbol():
    result = runner.invoke(filings_app, ["list", "600000.SH", "--root", str(FIXTURES_ROOT)])
    assert result.exit_code == 0
    assert "annual" in result.output.lower()
    assert "ipo" in result.output.lower()
    assert "research" in result.output.lower()


def test_show_annual():
    result = runner.invoke(filings_app, ["show", "600000.SH", "annual", "--year", "2024", "--root", str(FIXTURES_ROOT)])
    assert result.exit_code == 0
    assert "Annual 2024" in result.output


def test_show_missing_annual_exits_nonzero():
    result = runner.invoke(filings_app, ["show", "600000.SH", "annual", "--year", "1999", "--root", str(FIXTURES_ROOT)])
    assert result.exit_code != 0
```

Create `tests/unit/scripts/test_cli_profile.py`:
```python
from pathlib import Path

from typer.testing import CliRunner

from ah_research.scripts.ah_profile import profile_app

FIXTURES_ROOT = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "phase4_2" / "profiles"
runner = CliRunner()


def test_list_all():
    result = runner.invoke(profile_app, ["list", "--root", str(FIXTURES_ROOT)])
    assert result.exit_code == 0, result.output
    assert "600000.SH" in result.output


def test_show_latest():
    result = runner.invoke(profile_app, ["show", "600000.SH", "--root", str(FIXTURES_ROOT)])
    assert result.exit_code == 0
    assert "§1 能力圈" in result.output


def test_show_list_sections():
    result = runner.invoke(profile_app, ["show", "600000.SH", "--list-sections", "--root", str(FIXTURES_ROOT)])
    assert result.exit_code == 0
    assert "§1 能力圈" in result.output
    assert "§2 护城河" in result.output


def test_show_single_section():
    result = runner.invoke(profile_app, ["show", "600000.SH", "--section", "§1 能力圈", "--root", str(FIXTURES_ROOT)])
    assert result.exit_code == 0
    assert "圈内判断" in result.output


def test_show_unknown_symbol_nonzero():
    result = runner.invoke(profile_app, ["show", "999999.SH", "--root", str(FIXTURES_ROOT)])
    assert result.exit_code != 0
```

- [ ] **Step 4.2 — implement** `src/ah_research/scripts/ah_filings.py`:
```python
"""`ah filings` Typer sub-app."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from ah_research.filings.filings_repository import FilingsRepository

filings_app = typer.Typer(name="filings", help="Query local filings (年报 / 招股说明书 / 研报)")
console = Console()


@filings_app.command("list")
def list_filings(
    symbol: str | None = typer.Argument(None, help="Optional symbol filter."),
    root: Path = typer.Option(Path("data/filings"), help="Filings root directory."),
) -> None:
    repo = FilingsRepository(root=root)
    if symbol is None:
        table = Table(title="Filings (summary)")
        table.add_column("symbol")
        table.add_column("n_annual", justify="right")
        table.add_column("has_ipo")
        table.add_column("n_research", justify="right")
        for sym in repo.list_symbols():
            filings = repo.list_filings(sym)
            annual = sum(1 for f in filings if f.kind == "annual")
            ipo = any(f.kind == "ipo" for f in filings)
            research = sum(1 for f in filings if f.kind == "research")
            table.add_row(sym, str(annual), "true" if ipo else "false", str(research))
        console.print(table)
    else:
        filings = repo.list_filings(symbol)
        if not filings:
            console.print(f"[yellow]No filings found for {symbol}[/]")
            raise typer.Exit(code=0)
        table = Table(title=f"Filings for {symbol}")
        table.add_column("kind")
        table.add_column("year")
        table.add_column("title")
        table.add_column("path")
        for f in filings:
            table.add_row(
                f.kind,
                str(f.year) if f.year is not None else "-",
                f.title or "-",
                str(f.path),
            )
        console.print(table)


@filings_app.command("show")
def show_filing(
    symbol: str,
    kind: str = typer.Argument(..., help="annual | ipo | research"),
    year: int | None = typer.Option(None, help="Required for kind=annual."),
    root: Path = typer.Option(Path("data/filings"), help="Filings root directory."),
    full: bool = typer.Option(False, "--full", help="Print full text instead of head."),
    head_lines: int = typer.Option(80, help="Lines to print when not --full."),
) -> None:
    repo = FilingsRepository(root=root)
    text: str
    if kind == "annual":
        if year is None:
            raise typer.BadParameter("--year is required for kind=annual")
        f = repo.get_annual(symbol, year)
        text = f.text
    elif kind == "ipo":
        f2 = repo.get_ipo(symbol)
        if f2 is None:
            console.print(f"[red]No IPO prospectus for {symbol}[/]")
            raise typer.Exit(code=1)
        text = f2.text
    elif kind == "research":
        rs = repo.get_research(symbol)
        if not rs:
            console.print(f"[red]No research for {symbol}[/]")
            raise typer.Exit(code=1)
        text = "\n\n---\n\n".join(r.text for r in rs[:3])  # top 3 most recent
    else:
        raise typer.BadParameter("kind must be annual | ipo | research")
    if full:
        console.print(text)
    else:
        lines = text.splitlines()
        console.print("\n".join(lines[:head_lines]))
        if len(lines) > head_lines:
            console.print(f"[dim]... ({len(lines) - head_lines} more lines; use --full)[/]")
```

- [ ] **Step 4.3 — implement** `src/ah_research/scripts/ah_profile.py`:
```python
"""`ah profile` Typer sub-app."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from ah_research.filings.profile_repository import ProfileRepository

profile_app = typer.Typer(name="profile", help="Query value-investing profiles from profiles/")
console = Console()


@profile_app.command("list")
def list_profiles(
    symbol: str | None = typer.Argument(None, help="Optional symbol filter."),
    root: Path = typer.Option(Path("profiles"), help="Profiles root directory."),
) -> None:
    repo = ProfileRepository(root=root)
    if symbol is not None:
        profiles = repo.list_profiles(symbol)
    else:
        profiles = repo.list_profiles()
    if not profiles:
        console.print("[yellow]No profiles found[/]")
        raise typer.Exit(code=0)
    table = Table(title="Profiles")
    table.add_column("symbol")
    table.add_column("date")
    table.add_column("n_sections", justify="right")
    table.add_column("path")
    for p in profiles:
        table.add_row(p.symbol, p.date.isoformat(), str(len(p.sections)), str(p.path))
    console.print(table)


@profile_app.command("show")
def show_profile(
    symbol: str,
    date: str | None = typer.Option(None, help="ISO date (YYYY-MM-DD); defaults to latest."),
    section: str | None = typer.Option(None, help="Print only one named section."),
    list_sections: bool = typer.Option(False, "--list-sections", help="Print section headers only."),
    root: Path = typer.Option(Path("profiles"), help="Profiles root directory."),
) -> None:
    repo = ProfileRepository(root=root)
    if date is not None:
        from datetime import date as _date
        y, mo, d = map(int, date.split("-"))
        profile = repo.get(symbol, _date(y, mo, d))
    else:
        profile = repo.latest(symbol)
        if profile is None:
            console.print(f"[red]No profile found for {symbol}[/]")
            raise typer.Exit(code=1)
    if list_sections:
        for name in profile.sections:
            console.print(f"- {name}")
        return
    if section is not None:
        body = profile.sections.get(section)
        if body is None:
            console.print(f"[red]Section {section!r} not in profile (available: {list(profile.sections)[:5]}…)[/]")
            raise typer.Exit(code=1)
        console.print(body)
        return
    console.print(profile.text)
```

- [ ] **Step 4.4 — register sub-apps** in `src/ah_research/cli.py`. Find the existing Typer app and add:
```python
from ah_research.scripts.ah_filings import filings_app
from ah_research.scripts.ah_profile import profile_app

app.add_typer(filings_app)
app.add_typer(profile_app)
```
Place the imports near other sub-app imports; place the `add_typer` calls near other `add_typer` calls.

- [ ] **Step 4.5 — run**:
```bash
uv run pytest tests/unit/scripts/ -v
```
Expected: 9 passes.

- [ ] **Step 4.6 — smoke test the real CLI**:
```bash
uv run ah filings list 2>&1 | head -20
uv run ah profile list 2>&1 | head -20
```
Should print tables using the real `data/filings/600519.SH` + `profiles/600519.SH-2026-04-28.md`.

- [ ] **Step 4.7 — commit**
```bash
git add src/ah_research/scripts/ah_filings.py src/ah_research/scripts/ah_profile.py src/ah_research/cli.py tests/unit/scripts
git commit -m "feat(phase-4.2): ah filings + ah profile CLI sub-apps"
```

---

## Task 5: Acceptance notebook + headless test + real-data integration test

**Files:**
- Create: `notebooks/phase4_2_filings_example.ipynb`
- Create: `tests/integration/test_phase4_2_notebook_runs.py`
- Create: `tests/integration/test_filings_real_data.py`

- [ ] **Step 5.1 — generate the notebook**:
```bash
uv run python - <<'PY'
import json, pathlib
cells = [
    {"cell_type": "markdown", "metadata": {}, "source": ["# Phase 4.2 — Filings + Profile Repositories Example\n"]},
    {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": [
        "from ah_research.filings import FilingsRepository, ProfileRepository\n"
    ]},
    {"cell_type": "markdown", "metadata": {}, "source": ["## Filings"]},
    {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": [
        "fr = FilingsRepository()\n",
        "print('Symbols:', fr.list_symbols())\n",
        "filings = fr.list_filings('600519.SH')\n",
        "print(f'{len(filings)} filings for 600519.SH')\n",
        "for f in filings[:6]:\n",
        "    print(f'  {f.kind:8}  year={f.year}  title={f.title!r}  path={f.path.name}')\n"
    ]},
    {"cell_type": "markdown", "metadata": {}, "source": ["## Latest annual"]},
    {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": [
        "latest = fr.latest_annual('600519.SH')\n",
        "print(f'Year: {latest.year}')\n",
        "print(f'First 500 chars:\\n{latest.text[:500]}')\n"
    ]},
    {"cell_type": "markdown", "metadata": {}, "source": ["## Profiles"]},
    {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": [
        "pr = ProfileRepository()\n",
        "print('Profile symbols:', pr.list_symbols())\n",
        "profile = pr.latest('600519.SH')\n",
        "if profile is not None:\n",
        "    print(f'Date: {profile.date}  n_sections: {len(profile.sections)}')\n",
        "    for name in list(profile.sections)[:10]:\n",
        "        print(f'  - {name}')\n"
    ]},
    {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": [
        "assert fr.list_symbols(), 'no tickers under data/filings/'\n",
        "assert pr.list_symbols(), 'no profiles under profiles/'\n",
        "print('All checks passed')\n"
    ]},
]
nb = {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}}, "nbformat": 4, "nbformat_minor": 5}
pathlib.Path('notebooks/phase4_2_filings_example.ipynb').write_text(json.dumps(nb, indent=1))
print('wrote notebook')
PY
```

- [ ] **Step 5.2 — notebook test**:
```python
# tests/integration/test_phase4_2_notebook_runs.py
from __future__ import annotations

import pathlib

import nbformat
import pytest
from nbclient import NotebookClient

NOTEBOOKS_DIR = pathlib.Path(__file__).resolve().parents[2] / "notebooks"


def _run_notebook(nb_path: pathlib.Path) -> None:
    nb = nbformat.read(str(nb_path), as_version=4)
    client = NotebookClient(
        nb, timeout=600, kernel_name="python3",
        resources={"metadata": {"path": str(nb_path.parent.parent)}},
    )
    client.execute()
    for cell in nb.cells:
        if cell.cell_type != "code":
            continue
        for output in cell.get("outputs", []):
            assert output.get("output_type") != "error", f"Cell errored: {output}"


@pytest.mark.slow
def test_phase4_2_filings_example_notebook():
    _run_notebook(NOTEBOOKS_DIR / "phase4_2_filings_example.ipynb")
```

- [ ] **Step 5.3 — real-data integration test**:
```python
# tests/integration/test_filings_real_data.py
"""Sanity checks against the real data/filings/ + profiles/ on disk."""

from pathlib import Path

import pytest

from ah_research.filings import FilingsRepository, ProfileRepository

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_filings_repository_finds_600519():
    repo = FilingsRepository(root=REPO_ROOT / "data" / "filings")
    syms = repo.list_symbols()
    if "600519.SH" not in syms:
        pytest.skip("600519.SH not present locally")
    filings = repo.list_filings("600519.SH")
    assert sum(1 for f in filings if f.kind == "annual") >= 5
    assert any(f.kind == "ipo" for f in filings)


def test_profile_repository_finds_600519():
    repo = ProfileRepository(root=REPO_ROOT / "profiles")
    syms = repo.list_symbols()
    if "600519.SH" not in syms:
        pytest.skip("600519.SH profile not present locally")
    latest = repo.latest("600519.SH")
    assert latest is not None
    assert len(latest.sections) > 0
```

- [ ] **Step 5.4 — run**:
```bash
uv run pytest tests/integration/test_filings_real_data.py -v
uv run pytest tests/integration/test_phase4_2_notebook_runs.py -v -m slow
```
Expected: both pass.

- [ ] **Step 5.5 — commit**
```bash
git add notebooks/phase4_2_filings_example.ipynb tests/integration
git commit -m "feat(phase-4.2): acceptance notebook + real-data integration tests"
```

---

## Task 6: CHANGELOG + README + final verify

- [ ] **Step 6.1 — CHANGELOG entry** (prepend under the Phase 4.1 section in CHANGELOG.md):
```markdown
## Phase 4.2 — Filings + Profile Repositories (2026-04-30)

### Added
- `src/ah_research/filings/` package: `Filing` + `Profile` frozen dataclasses,
  `FilingsRepository` (indexes `data/filings/<ticker>/{年报,招股说明书,research}/*.md`),
  `ProfileRepository` (indexes `profiles/<ticker>-<date>.md` with markdown section parser).
- CLI sub-apps: `ah filings list/show`, `ah profile list/show [--section | --list-sections]`.
- Acceptance notebook `notebooks/phase4_2_filings_example.ipynb`.

### Design doc
- `docs/superpowers/specs/2026-04-30-ah-research-phase-4-2-filings-design.md`

### Deferred to Phase 4.3
- Dossier / Screener integration
- Structured grading of profile content (moat_grade, redflag_count, etc.)
```

- [ ] **Step 6.2 — README bullet** (append under Features):
```markdown
- **Phase 4.2: Filings + Profile Repositories** — `FilingsRepository`
  and `ProfileRepository` surface markdown artifacts (年报, 招股说明书,
  analyst research, value-investing profiles) as typed Python data.
  CLI: `ah filings list/show`, `ah profile list/show`.
  See [design spec](docs/superpowers/specs/2026-04-30-ah-research-phase-4-2-filings-design.md).
```

- [ ] **Step 6.3 — full verification**:
```bash
uv run pytest 2>&1 | tail -5
uv run mypy src 2>&1 | tail -5
uv run pre-commit run --files $(git diff --name-only origin/main..HEAD) 2>&1 | tail -10
```
Expected: all green.

- [ ] **Step 6.4 — commit**
```bash
git add CHANGELOG.md README.md
git commit -m "docs(phase-4.2): CHANGELOG + README entries"
```

- [ ] **Step 6.5 — push + create PR**
```bash
git push -u origin feat/phase-4.2
gh pr create --title "feat(phase-4.2): Filings + Profile Repositories" --body "$(cat <<'EOF'
## Summary

Phase 4.2 — surface the markdown artifacts produced by the value-profile skill
and filings downloader as typed Python data accessible from the `ah_research`
package and CLI.

- **`FilingsRepository`** — indexes `data/filings/<ticker>/{年报-YYYY.md, 招股说明书.md, research/*.md}` and returns `Filing` frozen dataclasses with typed `kind`, year/title/date.
- **`ProfileRepository`** — indexes `profiles/<ticker>-<date>.md` (skips `-evaluation.md`) with a markdown section parser that handles H2/H3 nesting and Chinese headers.
- **CLI:** `ah filings list/show`, `ah profile list/show [--section | --list-sections]`.
- **Acceptance notebook:** `phase4_2_filings_example.ipynb` runs headless in CI.

Design spec: `docs/superpowers/specs/2026-04-30-ah-research-phase-4-2-filings-design.md`

Deferred to Phase 4.3 (per spec §2 Out of scope): Dossier integration, Screener predicates backed by profile grades, structured grading / scoring of profile content. This phase intentionally ships read-only surface area — grading is a separate, harder problem.

## Test plan

- [x] Unit tests: types, FilingsRepository, ProfileRepository, CLI filings + profile
- [x] Integration: real-data sanity (600519.SH present) + notebook headless
- [x] Full suite + mypy green

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Acceptance checklist

- [ ] `uv run pytest` green
- [ ] `uv run mypy src` green
- [ ] Pre-commit clean
- [ ] Notebook runs headless
- [ ] `ah filings list` + `ah profile list` work on real clone
- [ ] PR created
