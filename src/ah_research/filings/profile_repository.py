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
            out.append(
                Profile(
                    symbol=sym,
                    date=_date(y, mo, d),
                    path=p,
                    text=text,
                    sections=parse_sections(text),
                )
            )
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
            symbol=symbol,
            date=date,
            path=path,
            text=text,
            sections=parse_sections(text),
        )


def parse_sections(md: str) -> Mapping[str, str]:
    """Parse markdown into section dict.

    - H2 headers (``^## ``) are top-level keys.
    - H3 headers (``^### ``) within a section are keyed as ``"<parent> / <sub>"``.
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
