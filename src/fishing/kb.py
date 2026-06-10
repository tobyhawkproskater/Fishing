"""High-level read-only query helpers over the SQLite knowledge base."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator, Optional

from . import KB_DIR

DB_PATH = KB_DIR / "fishing.sqlite"


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Knowledge base not built. Run `python -m fishing.build_kb` first."
        )
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        yield c
    finally:
        c.close()


def _rows(rows) -> list[dict]:
    return [dict(r) for r in rows]


# --- places / boat -----------------------------------------------------------

def places() -> list[dict]:
    with _conn() as c:
        return _rows(c.execute("SELECT * FROM place"))


def boat() -> Optional[dict]:
    with _conn() as c:
        r = c.execute("SELECT * FROM boat").fetchone()
        return dict(r) if r else None


# --- regulations -------------------------------------------------------------

def regulations(water: str, source: str = "both") -> dict:
    """Return current and/or proposed rule sections matching `water`.

    `source` ∈ {"current", "proposed", "both"}.
    """
    out: dict = {"current": [], "proposed": []}
    pat = f"%{water}%"
    with _conn() as c:
        if source in ("current", "both"):
            out["current"] = _rows(c.execute(
                "SELECT water, heading, page, text FROM rules_current "
                "WHERE water LIKE ? OR heading LIKE ? "
                "ORDER BY page",
                (pat, pat),
            ))
        if source in ("proposed", "both"):
            out["proposed"] = _rows(c.execute(
                "SELECT area, text FROM rules_proposed WHERE area LIKE ?",
                (pat,),
            ))
    return out


# --- calendar / species / gear / log ----------------------------------------

def calendar(water: Optional[str] = None, month: Optional[str] = None) -> list[dict]:
    sql = "SELECT * FROM calendar"
    args: tuple = ()
    if month:
        sql += " WHERE month LIKE ?"
        args = (f"%{month}%",)
    with _conn() as c:
        rows = _rows(c.execute(sql, args))
    if water:
        col = water.lower().replace(" ", "_")
        # narrow to month + the water column if it exists
        rows = [
            {"month": r["month"], water: r.get(col), "notes": r.get("notes")}
            for r in rows if r.get(col)
        ]
    return rows


def species(name: Optional[str] = None) -> list[dict]:
    with _conn() as c:
        if name:
            return _rows(c.execute(
                "SELECT * FROM species WHERE species LIKE ? OR subtype LIKE ?",
                (f"%{name}%", f"%{name}%"),
            ))
        return _rows(c.execute("SELECT * FROM species"))


def gear(use: Optional[str] = None) -> list[dict]:
    with _conn() as c:
        if use:
            return _rows(c.execute("SELECT * FROM gear WHERE use LIKE ?", (f"%{use}%",)))
        return _rows(c.execute("SELECT * FROM gear"))


def log_2025() -> list[dict]:
    with _conn() as c:
        return _rows(c.execute("SELECT * FROM log_2025 ORDER BY date"))


def meta() -> dict:
    with _conn() as c:
        return {r["key"]: r["value"] for r in c.execute("SELECT * FROM meta")}
