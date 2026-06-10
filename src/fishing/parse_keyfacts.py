"""Parse Key facts.docx → structured locations + boat."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from docx import Document

from . import SOURCES


@dataclass
class Place:
    name: str
    address: str


@dataclass
class Boat:
    year: int | None
    make: str
    model: str
    name: str


@dataclass
class KeyFacts:
    places: list[Place]
    boat: Boat | None


_ADDRESS_RE = re.compile(r"\d+\s+[\w. ]+,\s*[\w ]+,\s*[A-Z]{2},?\s*\d{5}")


def parse() -> KeyFacts:
    doc = Document(str(SOURCES["keyfacts"]))
    paras = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    text = "\n".join(paras)

    places: list[Place] = []
    label = None
    for line in paras:
        clean = line.rstrip(":").strip()
        if clean.lower().startswith("physical location of"):
            label = clean[len("physical location of "):].strip().rstrip(":")
            continue
        if label and _ADDRESS_RE.search(line):
            places.append(Place(name=label.title(), address=line))
            label = None

    boat = None
    for line in paras:
        if line.lower().startswith("boat"):
            m = re.search(r"(\d{4})\s+([A-Za-z. ]+?)\s+(\d+\s*\w[\w ]*),?\s*named\s+[\"\u201c]?([^\"\u201d]+)",
                          line, re.IGNORECASE)
            if m:
                boat = Boat(
                    year=int(m.group(1)),
                    make=m.group(2).strip(),
                    model=m.group(3).strip(),
                    name=m.group(4).strip(),
                )
            else:
                boat = Boat(year=None, make="", model=line, name="")
            break

    _ = text  # kept for debugging
    return KeyFacts(places=places, boat=boat)


def to_dict(kf: KeyFacts) -> dict:
    return {
        "places": [asdict(p) for p in kf.places],
        "boat": asdict(kf.boat) if kf.boat else None,
    }


if __name__ == "__main__":
    import json

    print(json.dumps(to_dict(parse()), indent=2))
