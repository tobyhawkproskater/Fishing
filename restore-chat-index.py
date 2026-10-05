"""Rebuild chat.ChatSessionStore.index in state.vscdb from chatSessions/*.jsonl.

Run with VS Code fully closed. Backs up state.vscdb before writing.
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import sqlite3
import sys
import time
from pathlib import Path

INDEX_KEY = "chat.ChatSessionStore.index"


def session_meta(jsonl_path: str) -> dict | None:
    sid = Path(jsonl_path).stem
    try:
        with open(jsonl_path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return None
    if not lines:
        return None

    try:
        head = json.loads(lines[0])
    except json.JSONDecodeError:
        return None
    v = head.get("v") or {}
    created = v.get("creationDate")
    initial_location = v.get("initialLocation", "panel")
    has_pending_edits = bool(v.get("hasPendingEdits", False))

    title = None
    first_user_text = None
    last_request_started = None
    last_request_ended = None
    last_message_date = None
    response_state = 0

    for raw in lines[1:]:
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        k = obj.get("k")
        kind = obj.get("kind")
        if kind == 1 and isinstance(k, list) and "customTitle" in k:
            title = obj.get("v")
        # heuristic: find first user request text for fallback title
        if first_user_text is None:
            val = obj.get("v")
            if isinstance(val, dict):
                txt = val.get("message") or val.get("text")
                if isinstance(txt, str) and txt.strip():
                    first_user_text = txt.strip().splitlines()[0][:60]
        # track latest timestamps anywhere
        for key in ("timestamp", "endTs", "startTs", "lastMessageDate"):
            ts = obj.get(key)
            if isinstance(ts, int):
                if key in ("endTs", "lastMessageDate"):
                    if last_request_ended is None or ts > last_request_ended:
                        last_request_ended = ts
                    if last_message_date is None or ts > last_message_date:
                        last_message_date = ts
                if key == "startTs":
                    if last_request_started is None or ts > last_request_started:
                        last_request_started = ts

    # mtime as last-resort timing
    mtime_ms = int(os.path.getmtime(jsonl_path) * 1000)
    if last_message_date is None:
        last_message_date = mtime_ms
    if last_request_started is None:
        last_request_started = last_message_date
    if last_request_ended is None:
        last_request_ended = last_message_date
    if created is None:
        created = mtime_ms

    if title is None:
        title = first_user_text or "(untitled session)"

    return {
        "sessionId": sid,
        "title": title,
        "lastMessageDate": last_message_date,
        "timing": {
            "created": created,
            "lastRequestStarted": last_request_started,
            "lastRequestEnded": last_request_ended,
        },
        "initialLocation": initial_location,
        "hasPendingEdits": has_pending_edits,
        "isEmpty": len(lines) <= 1,
        "isExternal": False,
        "lastResponseState": response_state,
        "permissionLevel": "default",
    }


def main(store_dir: str) -> int:
    db = os.path.join(store_dir, "state.vscdb")
    sessions_dir = os.path.join(store_dir, "chatSessions")
    if not os.path.exists(db):
        print(f"ERROR: state.vscdb missing at {db}")
        return 1
    if not os.path.isdir(sessions_dir):
        print(f"ERROR: chatSessions dir missing at {sessions_dir}")
        return 1

    # Build entries from disk
    entries: dict[str, dict] = {}
    for path in sorted(glob.glob(os.path.join(sessions_dir, "*.jsonl"))):
        meta = session_meta(path)
        if meta is None:
            print(f"  skip (unreadable): {os.path.basename(path)}")
            continue
        entries[meta["sessionId"]] = meta

    print(f"Found {len(entries)} session file(s) on disk.")

    # Backup db
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = f"{db}.bak-restore-{stamp}"
    shutil.copy2(db, backup)
    print(f"Backed up state.vscdb -> {os.path.basename(backup)}")

    # Merge with existing index (preserve any extra fields the live VS Code may have written)
    con = sqlite3.connect(db, timeout=5.0)
    try:
        row = con.execute(
            "SELECT value FROM ItemTable WHERE key = ?", (INDEX_KEY,)
        ).fetchone()
        if row is None:
            existing = {"version": 1, "entries": {}}
        else:
            try:
                existing = json.loads(row[0])
            except json.JSONDecodeError:
                existing = {"version": 1, "entries": {}}

        existing.setdefault("version", 1)
        existing_entries = existing.get("entries") or {}

        added = 0
        for sid, meta in entries.items():
            if sid in existing_entries:
                # keep existing live entry, do not overwrite
                continue
            existing_entries[sid] = meta
            added += 1
        existing["entries"] = existing_entries

        payload = json.dumps(existing, separators=(",", ":"))
        con.execute(
            "INSERT OR REPLACE INTO ItemTable(key, value) VALUES(?, ?)",
            (INDEX_KEY, payload),
        )
        con.commit()
    finally:
        con.close()

    print(f"Added {added} orphan session(s) to chat index.")
    print(f"Total index entries: {len(existing_entries)}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: restore-chat-index.py <workspaceStorage\\<id> path>")
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
