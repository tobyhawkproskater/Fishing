"""Build the knowledge base: write per-source JSON files and a SQLite DB."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from . import KB_DIR
from .parse_gear import parse_gear
from .parse_keyfacts import parse as parse_keyfacts, to_dict as keyfacts_to_dict
from .parse_proposed import parse as parse_proposed
from .parse_rules import parse as parse_rules


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def _build_sqlite(db_path: Path, kf, gear_wb, current, proposed, maps) -> None:
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    c.executescript(
        """
        CREATE TABLE place (name TEXT PRIMARY KEY, address TEXT);
        CREATE TABLE boat (year INTEGER, make TEXT, model TEXT, name TEXT);
        CREATE TABLE boat_spec (label TEXT, value TEXT, category TEXT, sort INTEGER);
        CREATE TABLE boat_note (topic TEXT, text TEXT, sort INTEGER);

        CREATE TABLE gear (
            use TEXT, purpose TEXT, brand TEXT, model TEXT, type TEXT,
            number TEXT, cost REAL, length TEXT, power TEXT, taper TEXT,
            line_rating TEXT, lure_rating TEXT, troll_rating TEXT,
            reel TEXT, line TEXT, guests TEXT, notes TEXT, location TEXT
        );

        CREATE TABLE rules_current (
            water TEXT, heading TEXT, page INTEGER, text TEXT
        );

        CREATE TABLE rules_proposed (
            area TEXT, text TEXT
        );

        CREATE TABLE map (
            id INTEGER PRIMARY KEY, title TEXT, filename TEXT, kind TEXT,
            source_url TEXT, local_path TEXT, bytes INTEGER, has_text INTEGER,
            text TEXT
        );
        CREATE TABLE map_ref (
            map_id INTEGER, kind TEXT, value TEXT
        );

        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        """
    )

    if kf:
        for p in kf.places:
            c.execute("INSERT INTO place VALUES (?, ?)", (p.name, p.address))
        if kf.boat:
            c.execute("INSERT INTO boat VALUES (?, ?, ?, ?)",
                      (kf.boat.year, kf.boat.make, kf.boat.model, kf.boat.name))
        for s in getattr(kf, "boat_specs", []) or []:
            c.execute("INSERT INTO boat_spec VALUES (?, ?, ?, ?)",
                      (s.label, s.value, s.category, s.sort))
        for n in getattr(kf, "boat_notes", []) or []:
            c.execute("INSERT INTO boat_note VALUES (?, ?, ?)",
                      (n.topic, n.text, n.sort))

    gear_cols = ["Use", "Purpose", "Brand", "Model", "Type", "Number",
                 "Cost (rod and reel)", "Length", "Power", "Taper",
                 "Line Rating", "Lure Rating", "Troll Rating",
                 "Reel", "Line", "Guests", "Notes", "Location"]
    for row in (gear_wb.get("rows") if gear_wb else []) or []:
        c.execute(
            f"INSERT INTO gear VALUES ({','.join('?' * len(gear_cols))})",
            tuple(row.get(col) for col in gear_cols),
        )

    for water, secs in (current.get("waters", {}) if current else {}).items():
        for s in secs:
            c.execute("INSERT INTO rules_current VALUES (?, ?, ?, ?)",
                      (water, s["heading"], s["page"], s["text"]))

    for s in (proposed.get("sections", []) if proposed else []):
        c.execute("INSERT INTO rules_proposed VALUES (?, ?)", (s["area"], s["text"]))

    for m in (maps.get("maps", []) if maps else []):
        c.execute(
            "INSERT INTO map (title, filename, kind, source_url, local_path, bytes, has_text, text) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (m.get("title"), m.get("filename"), m.get("kind", "map"), m.get("source_url"),
             m.get("local_path"), m.get("bytes", 0),
             1 if m.get("has_text") else 0, m.get("text", "")),
        )
        map_id = c.lastrowid
        for kind in ("waters", "spots", "places"):
            for value in m.get(kind, []) or []:
                c.execute("INSERT INTO map_ref VALUES (?, ?, ?)",
                          (map_id, kind[:-1], value))  # 'waters' -> 'water'

    if current:
        c.execute("INSERT INTO meta VALUES (?, ?)", ("rules_current_effective", current["effective"]))
    if proposed:
        c.execute("INSERT INTO meta VALUES (?, ?)", ("rules_proposed_source", proposed["source"]))
    if maps:
        c.execute("INSERT INTO meta VALUES (?, ?)", ("maps_source", maps.get("source", "")))

    conn.commit()
    conn.close()


def _safe(label: str, fn):
    """Call `fn()` and warn-skip if the source file is missing or malformed."""
    try:
        return fn()
    except FileNotFoundError as e:
        print(f"  WARN: {label} skipped (file missing: {e.filename})")
        return None
    except Exception as e:
        print(f"  WARN: {label} skipped ({type(e).__name__}: {e})")
        return None


def _load_maps() -> dict:
    """Load the maps catalog produced by `fishing.import_maps`."""
    path = KB_DIR / "maps.json"
    if not path.exists():
        raise FileNotFoundError(2, "No such file", str(path))
    return json.loads(path.read_text(encoding="utf-8"))


def _load_existing(name: str):
    """Load a previously-built KB JSON when live parsing isn't possible.

    The rules parsers need Xpdf's `pdftotext`; on machines without it, live
    parsing fails. Rather than drop the rules from the SQLite DB, fall back to
    the last committed JSON so the data stays queryable.
    """
    path = KB_DIR / name
    if path.exists():
        print(f"  using existing {name} (live parse unavailable)")
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def main() -> None:
    print("Parsing Key facts.docx...")
    kf = _safe("Key facts", parse_keyfacts)
    if kf:
        _write_json(KB_DIR / "locations.json", keyfacts_to_dict(kf))

    print("Parsing gear catalog...")
    gear_wb = _safe("Gear catalog", parse_gear)
    if gear_wb:
        _write_json(KB_DIR / "gear.json", gear_wb)

    print("Parsing proposed plan PDF...")
    proposed = _safe("Proposed plan PDF", parse_proposed)
    if proposed:
        _write_json(KB_DIR / "rules_proposed.json", proposed)
    else:
        proposed = _load_existing("rules_proposed.json")

    print("Parsing current rules PDF (this is the big one)...")
    current = _safe("Current rules PDF", parse_rules)
    if current:
        _write_json(KB_DIR / "rules_current.json", current)
    else:
        current = _load_existing("rules_current.json")

    print("Loading maps catalog (run `python -m fishing.import_maps` to build it)...")
    maps = _safe("Maps catalog", _load_maps)

    print("Building SQLite database...")
    db = KB_DIR / "fishing.sqlite"
    _build_sqlite(db, kf, gear_wb, current, proposed, maps)

    print(f"\nKnowledge base written to: {KB_DIR}")
    print(f"  SQLite: {db} ({db.stat().st_size // 1024} KB)")
    for f in sorted(KB_DIR.glob("*.json")):
        print(f"  {f.name}: {f.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
