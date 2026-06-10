"""Parse Proposed State Plan PDF → per-marine-area rule blocks.

The proposed plan is a fairly small document (~14 KB of text) with one section
per Marine Area. We segment by the "Marine Area N" headings and keep the raw
text for each — structured enough to look up by area, loose enough to survive
formatting quirks.
"""
from __future__ import annotations

import re

from . import SOURCES
from .pdf_text import extract_text

_MA_HEADER = re.compile(r"^(Marine Area\s+\d+(?:\.\d+)?|Tulalip Bubble|Elliott Bay|Sinclair Inlet|Bellingham Bay)\b",
                         re.MULTILINE)


def parse() -> dict:
    text = extract_text(SOURCES["rules_proposed_pdf"])

    # Find all section starts and slice.
    starts = [(m.start(), m.group(1)) for m in _MA_HEADER.finditer(text)]
    sections: list[dict] = []
    for i, (pos, name) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(text)
        body = text[pos:end].strip()
        sections.append({"area": name, "text": body})

    # Pull the document header (everything before the first MA section) as preamble.
    preamble = text[: starts[0][0]].strip() if starts else text.strip()

    return {
        "source": "Proposed State Plan.pdf",
        "preamble": preamble,
        "sections": sections,
    }


if __name__ == "__main__":
    import json

    data = parse()
    print(json.dumps({"preamble_len": len(data["preamble"]),
                      "sections": [s["area"] for s in data["sections"]]}, indent=2))
