"""Parse Key facts.docx → structured locations + boat (with loadout)."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

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
class BoatSpec:
    label: str
    value: str
    category: str
    sort: int = 0


@dataclass
class BoatNote:
    topic: str
    text: str
    sort: int = 0


@dataclass
class KeyFacts:
    places: list[Place]
    boat: Boat | None
    boat_specs: list[BoatSpec] = field(default_factory=list)
    boat_notes: list[BoatNote] = field(default_factory=list)


_ADDRESS_RE = re.compile(r"\d+\s+[\w. ]+,\s*[\w ]+,\s*[A-Z]{2},?\s*\d{5}")
_MOTOR_RE = re.compile(
    r"^(?P<year>\d{4})\s+(?P<make>[A-Za-z]+)\s+(?P<hp>\d+)\s*(?P<stroke>(?:four|two)\s*stroke\s+)?(?P<kind>outboard|kicker)",
    re.IGNORECASE,
)
_WIND_LIMIT_RE = re.compile(r"(\d+\s*-\s*\d+\s*MPH|\d+\s*MPH)", re.IGNORECASE)


def _classify_paragraph(line: str) -> tuple[str, str] | None:
    """Return (topic, normalized_text) for a prose paragraph after Boat: lines."""
    low = line.lower()
    if "mooring" in low or "dinghy" in low or "paddleboard" in low:
        return ("Mooring & tender access", line)
    if "tide" in low and ("glendale" in low or "hansville" in low or "useless bay" in low):
        return ("Local tide stations", line)
    if "marine area" in low and ("edmonds" in low or "kingston" in low or "mutiny" in low or "refuel" in low):
        return ("Home waters & refueling", line)
    if "wind" in low and ("mph" in low or "windy" in low):
        return ("Wind limits", line)
    if "gear is cataloged" in low or "spreadsheet" in low:
        return None  # obsolete reference to retired workbook
    return ("Notes", line)


def parse() -> KeyFacts:
    doc = Document(str(SOURCES["keyfacts"]))
    paras = [p.text.strip() for p in doc.paragraphs if p.text.strip()]

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

    boat: Boat | None = None
    boat_specs: list[BoatSpec] = []
    boat_notes: list[BoatNote] = []

    boat_line_idx = None
    for i, line in enumerate(paras):
        if line.lower().startswith("boat:"):
            boat_line_idx = i
            m = re.search(
                r"(\d{4})\s+([A-Za-z. ]+?)\s+(\d+\s*\w[\w ]*),?\s*named\s+[\"\u201c]?([^\"\u201d]+)",
                line, re.IGNORECASE,
            )
            if m:
                boat = Boat(
                    year=int(m.group(1)),
                    make=m.group(2).strip(),
                    model=m.group(3).strip(),
                    name=m.group(4).strip().rstrip("\u201d\""),
                )
            else:
                boat = Boat(year=None, make="", model=line, name="")
            break

    if boat_line_idx is not None:
        spec_sort = 0
        note_sort = 0
        for line in paras[boat_line_idx + 1:]:
            mm = _MOTOR_RE.search(line)
            if mm:
                kind = mm.group("kind").lower()
                spec_label = "Main outboard" if kind == "outboard" else "Kicker"
                value = f"{mm.group('year')} {mm.group('make').title()} {mm.group('hp')} HP"
                if mm.group("stroke"):
                    value += f" {mm.group('stroke').strip().lower()}"
                boat_specs.append(BoatSpec(label=spec_label, value=value,
                                           category="powertrain", sort=spec_sort))
                spec_sort += 1
                continue
            if "downrigger" in line.lower():
                boat_specs.append(BoatSpec(label="Downriggers", value=line,
                                           category="trolling", sort=spec_sort))
                spec_sort += 1
                continue
            classified = _classify_paragraph(line)
            if classified is None:
                continue
            topic, text = classified
            boat_notes.append(BoatNote(topic=topic, text=text, sort=note_sort))
            note_sort += 1

            wl = _WIND_LIMIT_RE.search(line) if "wind" in line.lower() else None
            if wl:
                boat_specs.append(BoatSpec(
                    label="Wind limit", value=wl.group(1).upper().replace(" ", ""),
                    category="limits", sort=spec_sort,
                ))
                spec_sort += 1

    return KeyFacts(places=places, boat=boat,
                    boat_specs=boat_specs, boat_notes=boat_notes)


def to_dict(kf: KeyFacts) -> dict:
    return {
        "places": [asdict(p) for p in kf.places],
        "boat": asdict(kf.boat) if kf.boat else None,
        "boat_specs": [asdict(s) for s in kf.boat_specs],
        "boat_notes": [asdict(n) for n in kf.boat_notes],
    }


if __name__ == "__main__":
    import json

    print(json.dumps(to_dict(parse()), indent=2))
