"""FilingsRepository — indexes data/filings/<ticker>/*.md and research subdir."""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date as _date
from pathlib import Path
from typing import TypedDict, get_args

from ah_research.filings.types import Filing, FilingKind
from ah_research.model.types import parse_symbol

_ANNUAL_RE = re.compile(r"^年报-(\d{4})\.md$")
_IPO_NAME = "招股说明书.md"
_RESEARCH_DATE_RE = re.compile(r"(\d{8})\.md$")
_VALID_KINDS: frozenset[str] = frozenset(get_args(FilingKind))
_MAX_LINE_LEN = 500

logger = logging.getLogger(__name__)


class _FilingStub(TypedDict):
    """Lightweight description of a filing path, used by search() before reading."""

    path: Path
    kind: FilingKind
    year: int | None
    title: str | None
    date: _date | None


@dataclass(frozen=True)
class SearchHit:
    """A single regex/substring match within a filing."""

    filing: Filing
    line_no: int  # 1-indexed
    line: str  # stripped, truncated to 500 chars + "…" if longer
    context: str  # 3 lines before + match + 3 lines after, joined with "\n"


class FilingsRepository:
    def __init__(self, root: Path = Path("data/filings")) -> None:
        self.root = Path(root)

    def list_symbols(self) -> list[str]:
        if not self.root.exists():
            return []
        return sorted(
            p.name
            for p in self.root.iterdir()
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
        return Filing(
            symbol=symbol,
            kind="annual",
            path=path,
            text=path.read_text(encoding="utf-8"),
            year=year,
        )

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
            out.append(
                Filing(
                    symbol=symbol,
                    kind="research",
                    path=p,
                    text=p.read_text(encoding="utf-8"),
                    title=p.stem,
                    date=_extract_date(p.name),
                )
            )
        return sorted(out, key=lambda f: f.date or _date.min, reverse=True)

    def search(
        self,
        query: str,
        *,
        symbols: Sequence[str] | None = None,
        kinds: Sequence[FilingKind] | None = None,
        regex: bool = False,
        max_hits_per_file: int | None = None,
    ) -> list[SearchHit]:
        """Search all filings for *query* (substring or regex).

        Ordering: symbol (alpha asc) → kind (annual, ipo, research)
        → within kind: year desc for annual, date desc for research
        → line_no asc.
        """
        if not query:
            raise ValueError("query must be non-empty")

        if kinds is not None:
            for k in kinds:
                if k not in _VALID_KINDS:
                    raise ValueError(f"Invalid kind {k!r}. Valid values: {sorted(_VALID_KINDS)}")

        # Compile pattern — let re.error bubble for invalid regex
        pattern = re.compile(query) if regex else re.compile(re.escape(query))

        # Determine which symbols to search
        target_symbols: list[str]
        if symbols is not None:
            # silently skip unknown tickers
            known = set(self.list_symbols())
            target_symbols = sorted(s for s in symbols if s in known)
        else:
            target_symbols = self.list_symbols()

        kind_order: dict[str, int] = {"annual": 0, "ipo": 1, "research": 2}

        hits: list[SearchHit] = []
        for sym in target_symbols:
            # Collect filing stubs (no text loaded) to avoid eager disk reads
            stubs = self._filing_stubs(sym)
            if kinds is not None:
                stubs = [s for s in stubs if s["kind"] in kinds]

            # Sort: kind order, then year desc / date desc within kind
            def _stub_sort_key(s: _FilingStub) -> tuple[int, int]:
                kind_rank = kind_order.get(s["kind"], 99)
                if s["kind"] == "annual":
                    return (kind_rank, -(s["year"] or 0))
                if s["kind"] == "research":
                    d = s["date"]
                    ts = (d - _date(1900, 1, 1)).days if d else 0
                    return (kind_rank, -ts)
                return (kind_rank, 0)

            stubs = sorted(stubs, key=_stub_sort_key)

            for stub in stubs:
                path: Path = stub["path"]
                try:
                    text = path.read_text(encoding="utf-8")
                except OSError as exc:
                    logger.warning("Cannot read %s: %s", path, exc)
                    continue

                # Build a Filing with the freshly read text
                filing = Filing(
                    symbol=sym,
                    kind=stub["kind"],
                    path=path,
                    text=text,
                    year=stub["year"],
                    title=stub["title"],
                    date=stub["date"],
                )

                lines = text.splitlines()
                file_hits = 0
                for i, raw_line in enumerate(lines):
                    line_no = i + 1
                    if max_hits_per_file is not None and file_hits >= max_hits_per_file:
                        break
                    if not pattern.search(raw_line):
                        continue

                    # Truncate long lines
                    stripped = raw_line.strip()
                    if len(stripped) > _MAX_LINE_LEN:
                        display_line = stripped[:_MAX_LINE_LEN] + "…"
                    else:
                        display_line = stripped

                    # Build context window (3 before + match + 3 after)
                    ctx_start = max(0, i - 3)
                    ctx_end = min(len(lines), i + 4)
                    context = "\n".join(lines[ctx_start:ctx_end])

                    hits.append(
                        SearchHit(
                            filing=filing,
                            line_no=line_no,
                            line=display_line,
                            context=context,
                        )
                    )
                    file_hits += 1

        return hits

    # -- internals -----------------------------------------------------------

    def _filing_stubs(self, symbol: str) -> list[_FilingStub]:
        """Return lightweight dicts describing each filing path without reading text.

        Each dict has keys: path, kind, year, title, date.
        Used by search() to enumerate files before attempting to read them,
        so that OSError on a single file is caught per-file inside search().
        """
        sym_dir = self.root / symbol
        if not sym_dir.exists():
            return []
        stubs: list[_FilingStub] = []

        # Annuals
        for p in sorted(sym_dir.iterdir()):
            m = _ANNUAL_RE.match(p.name)
            if m:
                stubs.append(
                    {
                        "path": p,
                        "kind": "annual",
                        "year": int(m.group(1)),
                        "title": None,
                        "date": None,
                    }
                )

        # IPO
        ipo_path = sym_dir / _IPO_NAME
        if ipo_path.exists():
            stubs.append(
                {"path": ipo_path, "kind": "ipo", "year": None, "title": None, "date": None}
            )

        # Research
        rdir = sym_dir / "research"
        if rdir.exists():
            for p in sorted(rdir.glob("*.md")):
                stubs.append(
                    {
                        "path": p,
                        "kind": "research",
                        "year": None,
                        "title": p.stem,
                        "date": _extract_date(p.name),
                    }
                )

        return stubs

    def _annuals(self, symbol: str, sym_dir: Path) -> list[Filing]:
        out: list[Filing] = []
        for p in sorted(sym_dir.iterdir()):
            m = _ANNUAL_RE.match(p.name)
            if m:
                year = int(m.group(1))
                out.append(
                    Filing(
                        symbol=symbol,
                        kind="annual",
                        path=p,
                        text=p.read_text(encoding="utf-8"),
                        year=year,
                    )
                )
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
            out.append(
                Filing(
                    symbol=symbol,
                    kind="research",
                    path=p,
                    text=p.read_text(encoding="utf-8"),
                    title=p.stem,
                    date=_extract_date(p.name),
                )
            )
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
