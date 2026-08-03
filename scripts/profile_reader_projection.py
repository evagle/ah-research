"""Project canonical profile Markdown into reader-only Markdown."""

from __future__ import annotations

import re
from dataclasses import dataclass

COMMENT_PATTERN = re.compile(r"<!--.*?-->", re.DOTALL)
READER_EXCLUDE_SECTION_MARKER = "<!-- reader-exclude-section -->"
READER_METADATA_PATTERN = re.compile(
    r"^\s*\*\*(引用|置信度|管理层口径校核)[:：]\*\*(.*)$",
)
HEADING_PATTERN = re.compile(r"^(#{2,6})\s+\S")
TABLE_LINE_PATTERN = re.compile(r"^\s*\|.*\|\s*$")
SEPARATOR_PATTERN = re.compile(r"^\s*(?:---+|\*\*\*+|___+)\s*$")
FINGERPRINT_PATTERN = re.compile(r"(?<![0-9a-f])[0-9a-f]{40,64}(?![0-9a-f])", re.I)
ABSOLUTE_PATH_PATTERN = re.compile(r"(?:/Users/|/home/)[^\s`|]+")
MACHINE_KEY_PATTERN = re.compile(
    r"\b(?:schema_version|claim_states|route_status|ledger_path|"
    r"market_definition_fingerprint|series_fingerprint)\b",
    re.I,
)
MACHINE_PARAGRAPH_PATTERN = re.compile(
    r"(?:原口径指纹|主口径指纹|路由终态|恢复账本|角色状态|"
    r"claim状态|role状态|bundle状态|ledger\s+path)",
    re.I,
)
WORKFLOW_STATE_PATTERN = re.compile(
    r"(?:(?:accepted|partial|blocked|exhausted).{0,30}(?:claim|role|route|状态|路由)"
    r"|(?:claim|role|route|状态|路由).{0,30}"
    r"(?:accepted|partial|blocked|exhausted))",
    re.I,
)
MACHINE_TABLE_TERMS = (
    "原口径指纹",
    "主口径指纹",
    "路由终态",
    "下一步所需证据",
    "schema版本",
    "schema version",
    "claim状态",
    "role状态",
    "ledger",
)
VISIBLE_LEAK_PATTERNS = (
    COMMENT_PATTERN,
    FINGERPRINT_PATTERN,
    ABSOLUTE_PATH_PATTERN,
    MACHINE_KEY_PATTERN,
    MACHINE_PARAGRAPH_PATTERN,
    WORKFLOW_STATE_PATTERN,
    re.compile(r"机器引用清单"),
)


@dataclass(frozen=True, slots=True)
class Removal:
    """A machine-only source block removed from the reader projection."""

    category: str
    start_line: int
    end_line: int
    summary: str


@dataclass(frozen=True, slots=True)
class ProjectionResult:
    """Reader Markdown and an audit of deterministic removals."""

    markdown: str
    removals: tuple[Removal, ...]


def _summary(lines: list[str], start: int, end: int) -> str:
    text = " ".join(line.strip() for line in lines[start : end + 1] if line.strip())
    text = re.sub(r"\s+", " ", text)
    return text[:96] or "(empty block)"


def _blank_comments(source: str) -> tuple[str, list[tuple[int, int, str]]]:
    comments: list[tuple[int, int, str]] = []

    def replace(match: re.Match[str]) -> str:
        start_line = source.count("\n", 0, match.start()) + 1
        end_line = source.count("\n", 0, match.end()) + 1
        summary = re.sub(r"\s+", " ", match.group()).strip()[:96]
        comments.append((start_line, end_line, summary))
        return "".join("\n" if character == "\n" else " " for character in match.group())

    return COMMENT_PATTERN.sub(replace, source), comments


def _blank_reader_excluded_sections(
    source: str,
) -> tuple[str, list[tuple[int, int, str]]]:
    lines = source.splitlines(keepends=True)
    exclusions: list[tuple[int, int, str]] = []
    index = 0

    while index < len(lines):
        heading = re.match(r"^(#{2,6})\s+(.+?)\s*$", lines[index].rstrip("\r\n"))
        if heading is None:
            index += 1
            continue

        marker_index = index + 1
        while marker_index < len(lines) and not lines[marker_index].strip():
            marker_index += 1
        if (
            marker_index >= len(lines)
            or lines[marker_index].strip() != READER_EXCLUDE_SECTION_MARKER
        ):
            index += 1
            continue

        heading_level = len(heading.group(1))
        end = marker_index + 1
        while end < len(lines):
            next_heading = re.match(r"^(#{2,6})\s+\S", lines[end])
            if next_heading is not None and len(next_heading.group(1)) <= heading_level:
                break
            end += 1

        exclusions.append((index + 1, end, heading.group(2)))
        for line_index in range(index, end):
            lines[line_index] = "".join(
                "\n" if character == "\n" else "\r" if character == "\r" else " "
                for character in lines[line_index]
            )
        index = end

    return "".join(lines), exclusions


def _is_machine_paragraph(text: str) -> bool:
    return any(
        pattern.search(text)
        for pattern in (
            FINGERPRINT_PATTERN,
            ABSOLUTE_PATH_PATTERN,
            MACHINE_KEY_PATTERN,
            MACHINE_PARAGRAPH_PATTERN,
            WORKFLOW_STATE_PATTERN,
        )
    )


def _is_machine_table(lines: list[str]) -> bool:
    text = "\n".join(lines)
    normalized = text.lower()
    return FINGERPRINT_PATTERN.search(text) is not None or any(
        term.lower() in normalized for term in MACHINE_TABLE_TERMS
    )


def _clean_structure(lines: list[str]) -> list[str]:
    cleaned = [line.rstrip() for line in lines]

    last_content = len(cleaned) - 1
    while last_content >= 0 and not cleaned[last_content].strip():
        last_content -= 1
    if last_content >= 0 and HEADING_PATTERN.match(cleaned[last_content]):
        del cleaned[last_content:]

    compacted: list[str] = []
    blank_count = 0
    for line in cleaned:
        if line.strip():
            if SEPARATOR_PATTERN.match(line) and (
                not compacted or SEPARATOR_PATTERN.match(compacted[-1])
            ):
                continue
            compacted.append(line)
            blank_count = 0
            continue
        blank_count += 1
        if blank_count <= 1 and compacted:
            compacted.append("")

    while compacted and not compacted[-1].strip():
        compacted.pop()
    return compacted


def find_reader_leaks(source: str) -> tuple[str, ...]:
    """Return known machine-only patterns still present in reader content."""

    leaks: list[str] = []
    for pattern in VISIBLE_LEAK_PATTERNS:
        match = pattern.search(source)
        if match is not None:
            leaks.append(re.sub(r"\s+", " ", match.group()).strip()[:96])
    return tuple(leaks)


def assert_reader_only(source: str) -> None:
    """Reject reader content that still contains a known machine-only marker."""

    leaks = find_reader_leaks(source)
    if leaks:
        raise ValueError(f"reader projection still contains machine-only content: {leaks[0]}")


def format_removal(removal: Removal) -> str:
    """Format one concise console record."""

    location = (
        f"line {removal.start_line}"
        if removal.start_line == removal.end_line
        else f"lines {removal.start_line}-{removal.end_line}"
    )
    return f"[reader-projection] removed {removal.category} {location}: {removal.summary}"


def project_reader_markdown(source: str) -> ProjectionResult:
    """Remove machine-only Markdown blocks and return a validated reader projection."""

    without_excluded_sections, exclusion_records = _blank_reader_excluded_sections(source)
    without_comments, comment_records = _blank_comments(without_excluded_sections)
    lines = without_comments.splitlines()
    original_lines = source.splitlines()
    removed: set[int] = set()
    removals = [
        Removal("reader-excluded-section", start, end, summary)
        for start, end, summary in exclusion_records
    ] + [Removal("html-comment", start, end, summary) for start, end, summary in comment_records]

    index = 0
    while index < len(lines):
        metadata = READER_METADATA_PATTERN.match(lines[index].strip())
        if metadata is None:
            index += 1
            continue

        end = index
        if metadata.group(1) == "引用" and not metadata.group(2).strip():
            cursor = index + 1
            while cursor < len(lines):
                stripped = lines[cursor].strip()
                if (
                    not stripped
                    or re.match(r"^[-*+]\s+", stripped)
                    or lines[cursor].startswith((" ", "\t"))
                ):
                    end = cursor
                    cursor += 1
                    continue
                break
        removed.update(range(index, end + 1))
        removals.append(
            Removal(
                "reader-metadata",
                index + 1,
                end + 1,
                _summary(original_lines, index, end),
            )
        )
        index = end + 1

    index = 0
    while index < len(lines):
        if index in removed or not TABLE_LINE_PATTERN.match(lines[index]):
            index += 1
            continue
        end = index
        while end + 1 < len(lines) and TABLE_LINE_PATTERN.match(lines[end + 1]):
            end += 1
        if _is_machine_table(lines[index : end + 1]):
            removed.update(range(index, end + 1))
            removals.append(
                Removal(
                    "machine-table",
                    index + 1,
                    end + 1,
                    _summary(original_lines, index, end),
                )
            )
        index = end + 1

    index = 0
    while index < len(lines):
        if index in removed or not lines[index].strip():
            index += 1
            continue
        end = index
        while end + 1 < len(lines) and lines[end + 1].strip() and end + 1 not in removed:
            end += 1
        paragraph = "\n".join(lines[index : end + 1])
        if _is_machine_paragraph(paragraph):
            removed.update(range(index, end + 1))
            removals.append(
                Removal(
                    "machine-paragraph",
                    index + 1,
                    end + 1,
                    _summary(original_lines, index, end),
                )
            )
        index = end + 1

    projected_lines = [line for line_number, line in enumerate(lines) if line_number not in removed]
    markdown = "\n".join(_clean_structure(projected_lines))
    if markdown:
        markdown += "\n"
    if not re.search(r"[\w\u3400-\u9fff]", markdown):
        raise ValueError("reader projection is empty")
    assert_reader_only(markdown)
    return ProjectionResult(markdown=markdown, removals=tuple(removals))
