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


def _build_sqlite(db_path: Path, kf, gear_wb, current, proposed) -> None:
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

    if current:
        c.execute("INSERT INTO meta VALUES (?, ?)", ("rules_current_effective", current["effective"]))
    if proposed:
        c.execute("INSERT INTO meta VALUES (?, ?)", ("rules_proposed_source", proposed["source"]))

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

    print("Parsing current rules PDF (this is the big one)...")
    current = _safe("Current rules PDF", parse_rules)
    if current:
        _write_json(KB_DIR / "rules_current.json", current)

    print("Building SQLite database...")
    db = KB_DIR / "fishing.sqlite"
    _build_sqlite(db, kf, gear_wb, current, proposed)

    print(f"\nKnowledge base written to: {KB_DIR}")
    print(f"  SQLite: {db} ({db.stat().st_size // 1024} KB)")
    for f in sorted(KB_DIR.glob("*.json")):
        print(f"  {f.name}: {f.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
