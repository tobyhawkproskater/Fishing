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


def boat_specs() -> list[dict]:
    with _conn() as c:
        return _rows(c.execute(
            "SELECT label, value, category, sort FROM boat_spec ORDER BY sort"
        ))


def boat_notes() -> list[dict]:
    with _conn() as c:
        return _rows(c.execute(
            "SELECT topic, text, sort FROM boat_note ORDER BY sort"
        ))


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


# --- gear -------------------------------------------------------------------

def gear(use: Optional[str] = None) -> list[dict]:
    with _conn() as c:
        if use:
            return _rows(c.execute("SELECT * FROM gear WHERE use LIKE ?", (f"%{use}%",)))
        return _rows(c.execute("SELECT * FROM gear"))


def meta() -> dict:
    with _conn() as c:
        return {r["key"]: r["value"] for r in c.execute("SELECT * FROM meta")}
