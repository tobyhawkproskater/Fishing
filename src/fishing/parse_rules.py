"""Parse the WDFW Sport Fishing Rules pamphlet PDF.

The full pamphlet covers all of Washington. We only care about a handful of
waters, so we segment by section heading and keep just the ones relevant to
this household. Adding more waters later is just a matter of appending to
`WATERS_OF_INTEREST`.

Strategy:
1. Extract all pages of text.
2. Detect section headings (UPPERCASE name followed by " - <COUNTY> CO." or
   "Marine Area N" lines).
3. Return per-water raw text blocks plus a few derived fields (current pamphlet
   period, source page numbers).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import SOURCES
from .pdf_text import extract_text

# Names to slice out of the pamphlet. Match is case-insensitive on a line-start.
WATERS_OF_INTEREST: list[str] = [
    "SKYKOMISH RIVER",
    "SKYKOMISH RIVER, NORTH FORK",
    "SKYKOMISH RIVER, SOUTH FORK",
    "WALLACE RIVER",
    "SNOHOMISH RIVER",
    "PILCHUCK RIVER",
    "SNOQUALMIE RIVER",
    "TOKUL CREEK",
    "LAKE SAMMAMISH",
    "SAMMAMISH, LAKE",
    "SAMMAMISH RIVER",
    "Marine Area 9",
    "Marine Area 10",
]

# Heading patterns we recognize. pdftotext -layout sometimes concatenates
# adjacent columns onto one line, so a heading may appear either alone or
# tacked on the end of another row. We use non-anchored patterns and just
# look line-by-line for any occurrence.
_FRESHWATER_HEADING = re.compile(
    r"([A-Z][A-Z0-9 ,'.()/-]{3,60}?)\s+-\s+([A-Z][A-Z /]+?CO\.?)(?:\s|$)"
)
_MARINE_HEADING = re.compile(
    r"(Marine Area\s+\d+(?:\.\d+)?(?:\s*[-\u2013]\s*[A-Za-z][A-Za-z /]+|\s+[A-Z][A-Za-z][A-Za-z /]+?)?)(?:\s\(continued\))?\s*$"
)


@dataclass
class Section:
    name: str
    page: int
    text: str


_PAGE_BREAK = "\x0c"


def _extract_pages() -> list[tuple[int, str]]:
    """Return (page_number, text) for each page.

    pdftotext emits a form-feed (\\x0c) between pages, which we use to split.
    """
    full = extract_text(SOURCES["rules_current_pdf"])
    pages: list[tuple[int, str]] = []
    for i, chunk in enumerate(full.split(_PAGE_BREAK), start=1):
        pages.append((i, chunk))
    return pages


def _find_sections(pages: list[tuple[int, str]]) -> list[Section]:
    """Walk the document line-by-line and slice at every heading we recognize.

    The pamphlet is multi-column; pdftotext -layout occasionally concatenates
    rows from adjacent columns onto one line, so a heading can appear at the
    start of a line or tacked onto the end. We accept both.
    """
    # Build a flat list of (page_number, line_text).
    flat: list[tuple[int, str]] = []
    for pno, text in pages:
        for line in text.splitlines():
            flat.append((pno, line))

    # First pass: identify lines that contain a section heading.
    headings: list[tuple[int, int, str]] = []  # (line_index, page, name)
    for idx, (pno, line) in enumerate(flat):
        m = _FRESHWATER_HEADING.search(line)
        if m:
            name = f"{m.group(1).strip()} - {m.group(2).strip()}"
            headings.append((idx, pno, name))
            continue
        ma = _MARINE_HEADING.search(line.strip())
        if ma and "Marine Area" in line:
            name = ma.group(1).strip()
            headings.append((idx, pno, name))

    # Second pass: slice text from each heading to the next.
    sections: list[Section] = []
    for i, (line_idx, page, name) in enumerate(headings):
        end_line = headings[i + 1][0] if i + 1 < len(headings) else len(flat)
        body_lines = [ln for _, ln in flat[line_idx:end_line]]
        sections.append(Section(name=name, page=page, text="\n".join(body_lines).strip()))
    return sections


def _matches_interest(name: str) -> str | None:
    up = name.upper()
    for target in WATERS_OF_INTEREST:
        t = target.upper()
        if up == t or up.startswith(t + " -") or up.startswith(t + ","):
            return target
        if t in up and len(up) - len(t) < 30:
            return target
    return None


def parse() -> dict:
    pages = _extract_pages()
    all_sections = _find_sections(pages)

    kept: dict[str, list[dict]] = {}
    for s in all_sections:
        bucket = _matches_interest(s.name)
        if not bucket:
            continue
        kept.setdefault(bucket, []).append(
            {"heading": s.name, "page": s.page, "text": s.text}
        )

    return {
        "source": "Washington State Rules.pdf",
        "effective": "2025-07-01 to 2026-06-30",
        "waters": kept,
        "section_count_total": len(all_sections),
    }


if __name__ == "__main__":
    import json

    data = parse()
    summary = {k: [s["heading"] for s in v] for k, v in data["waters"].items()}
    print(json.dumps({"section_count_total": data["section_count_total"],
                      "waters": summary}, indent=2))
