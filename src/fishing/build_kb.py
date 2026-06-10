"""Build the knowledge base: write per-source JSON files and a SQLite DB."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from . import KB_DIR
from .parse_keyfacts import parse as parse_keyfacts, to_dict as keyfacts_to_dict
from .parse_proposed import parse as parse_proposed
from .parse_rules import parse as parse_rules
from .parse_workbook import parse as parse_workbook


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def _build_sqlite(db_path: Path, kf, wb, current, proposed) -> None:
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    c.executescript(
        """
        CREATE TABLE place (name TEXT PRIMARY KEY, address TEXT);
        CREATE TABLE boat (year INTEGER, make TEXT, model TEXT, name TEXT);

        CREATE TABLE species (
            family TEXT, species TEXT, subtype TEXT, scientific_name TEXT,
            native_to_basin TEXT, definition TEXT, hatchery TEXT,
            life_history TEXT, ocean_years TEXT,
            outmigration_timing TEXT, ocean_entry_timing TEXT,
            return_timing TEXT, peak_spawning_window TEXT,
            peak_fishing_opportunity TEXT, typical_size_range TEXT,
            preferred_prey TEXT, seasonal_behavior_notes TEXT,
            ma9 TEXT, ma10 TEXT, skykomish TEXT, snohomish TEXT,
            snoqualmie TEXT, lake_sammamish TEXT,
            peak_saltwater_window TEXT, peak_river_window TEXT, notes TEXT
        );

        CREATE TABLE calendar (
            month TEXT, ma9 TEXT, ma10 TEXT, skykomish TEXT,
            snohomish TEXT, snoqualmie TEXT, lake_sammamish TEXT, notes TEXT
        );

        CREATE TABLE gear (
            use TEXT, type TEXT, brand TEXT, model TEXT, number TEXT,
            cost REAL, length TEXT, power TEXT, taper TEXT,
            line_rating TEXT, lure_rating TEXT, troll_rating TEXT,
            reel TEXT, line TEXT, guests TEXT, notes TEXT, location TEXT
        );

        CREATE TABLE log_2025 (
            date TEXT, fish INTEGER, pink INTEGER, coho INTEGER,
            chinook INTEGER, hours REAL, notes TEXT
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

    for p in kf.places:
        c.execute("INSERT INTO place VALUES (?, ?)", (p.name, p.address))
    if kf.boat:
        c.execute("INSERT INTO boat VALUES (?, ?, ?, ?)",
                  (kf.boat.year, kf.boat.make, kf.boat.model, kf.boat.name))

    species_cols = [
        "Family", "Species", "Subtype", "Scientific Name", "Native to Basin",
        "Definition", "Hatchery?", "Life History Strategy", "Ocean Years",
        "Outmigration Timing", "Ocean Entry Timing", "Return Timing",
        "Peak Spawning Window", "Peak Fishing Opportunity", "Typical Size Range",
        "Preferred Prey", "Seasonal Behavior Notes",
        "MA9 Opportunity", "MA10 Opportunity", "Skykomish Opportunity",
        "Snohomish Opportunity", "Snoqualmie Opportunity",
        "Lake Sammamish Opportunity", "Peak Saltwater Window",
        "Peak River Window", "Notes",
    ]
    for row in wb["species"]["rows"]:
        c.execute(
            f"INSERT INTO species VALUES ({','.join('?' * len(species_cols))})",
            tuple(row.get(col) for col in species_cols),
        )

    cal_cols = ["Month", "MA9", "MA10", "Skykomish", "Snohomish",
                "Snoqualmie", "Lake Sammamish", "Notes"]
    for row in wb["calendar"]["rows"]:
        c.execute(
            f"INSERT INTO calendar VALUES ({','.join('?' * len(cal_cols))})",
            tuple(row.get(col) for col in cal_cols),
        )

    gear_cols = ["Use", "Type", "Brand", "Model", "Number", "Cost (rod and reel)",
                 "Length", "Power", "Taper", "Line Rating", "Lure Rating",
                 "Troll Rating", "Reel", "Line", "Guests", "Notes", "Location"]
    for row in wb["gear"]["rows"]:
        c.execute(
            f"INSERT INTO gear VALUES ({','.join('?' * len(gear_cols))})",
            tuple(row.get(col) for col in gear_cols),
        )

    log_cols = ["Date", "Fish", "Pink", "Coho", "Chinook", "Hours", "Notes"]
    for row in wb["log_2025"]["rows"]:
        c.execute(
            f"INSERT INTO log_2025 VALUES ({','.join('?' * len(log_cols))})",
            tuple(row.get(col) for col in log_cols),
        )

    for water, secs in current["waters"].items():
        for s in secs:
            c.execute("INSERT INTO rules_current VALUES (?, ?, ?, ?)",
                      (water, s["heading"], s["page"], s["text"]))

    for s in proposed["sections"]:
        c.execute("INSERT INTO rules_proposed VALUES (?, ?)", (s["area"], s["text"]))

    c.execute("INSERT INTO meta VALUES (?, ?)", ("rules_current_effective", current["effective"]))
    c.execute("INSERT INTO meta VALUES (?, ?)", ("rules_proposed_source", proposed["source"]))

    conn.commit()
    conn.close()


def main() -> None:
    print("Parsing Key facts.docx...")
    kf = parse_keyfacts()
    _write_json(KB_DIR / "locations.json", keyfacts_to_dict(kf))

    print("Parsing workbook...")
    wb = parse_workbook()
    for key in wb:
        _write_json(KB_DIR / f"{key}.json", wb[key])

    print("Parsing proposed plan PDF...")
    proposed = parse_proposed()
    _write_json(KB_DIR / "rules_proposed.json", proposed)

    print("Parsing current rules PDF (this is the big one)...")
    current = parse_rules()
    _write_json(KB_DIR / "rules_current.json", current)

    print("Building SQLite database...")
    db = KB_DIR / "fishing.sqlite"
    _build_sqlite(db, kf, wb, current, proposed)

    print(f"\nKnowledge base written to: {KB_DIR}")
    print(f"  SQLite: {db} ({db.stat().st_size // 1024} KB)")
    for f in sorted(KB_DIR.glob("*.json")):
        print(f"  {f.name}: {f.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
