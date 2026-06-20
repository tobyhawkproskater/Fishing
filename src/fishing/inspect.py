"""Quick CLI to peek at the built knowledge base."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from . import KB_DIR

DB = KB_DIR / "fishing.sqlite"


def _connect() -> sqlite3.Connection:
    if not DB.exists():
        raise SystemExit(f"No DB at {DB} — run `python -m fishing.build_kb` first.")
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def _print_rows(rows, max_cols: int = 6) -> None:
    for r in rows:
        keys = list(r.keys())[:max_cols]
        print(" | ".join(f"{k}={r[k]}" for k in keys))


def summary() -> None:
    conn = _connect()
    print(f"DB: {DB}")
    for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        n = conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        print(f"  {name:<16} {n:>4} rows")
    print()
    print("Places:")
    _print_rows(conn.execute("SELECT * FROM place"))
    print("Boat:")
    _print_rows(conn.execute("SELECT * FROM boat"))


def dump(table: str) -> None:
    conn = _connect()
    rows = list(conn.execute(f"SELECT * FROM {table} LIMIT 50"))
    _print_rows(rows, max_cols=10)
    print(f"\n({len(rows)} rows shown)")


def rules(area: str) -> None:
    conn = _connect()
    print(f"=== Current rules matching '{area}' ===")
    for r in conn.execute(
        "SELECT water, heading, page FROM rules_current WHERE water LIKE ? OR heading LIKE ?",
        (f"%{area}%", f"%{area}%"),
    ):
        print(f"  p.{r['page']:>4}  {r['water']}  |  {r['heading']}")
    print(f"\n=== Proposed rules matching '{area}' ===")
    for r in conn.execute("SELECT area FROM rules_proposed WHERE area LIKE ?", (f"%{area}%",)):
        print(f"  {r['area']}")


def main(argv: list[str]) -> None:
    if not argv:
        summary()
        return
    cmd, *rest = argv
    if cmd == "rules" and rest:
        rules(rest[0])
    elif cmd in {"gear", "rules_current", "rules_proposed", "place", "boat"}:
        dump(cmd)
    else:
        print(__doc__)
        print("Usage: python -m fishing.inspect [summary|gear"
              "|rules_current|rules_proposed|rules <area>]")


if __name__ == "__main__":
    main(sys.argv[1:])
