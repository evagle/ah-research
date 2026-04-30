"""FilingsRepository — indexes data/filings/<ticker>/*.md and research subdir."""

from __future__ import annotations

import re
from datetime import date as _date
from pathlib import Path

from ah_research.filings.types import Filing
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

    # -- internals -----------------------------------------------------------

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
