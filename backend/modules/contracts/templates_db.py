"""
modules/contracts/templates_db.py — contract template persistence.

Table: contract_templates
  id            INTEGER PRIMARY KEY
  uid           TEXT    — owner
  name          TEXT    — display name
  position      TEXT    — selling/buying/exchanging/trading/vouchcopy
  terms         TEXT    — full terms BBCode
  yourproduct   TEXT
  yourcurrency  TEXT
  youramount    TEXT
  theirproduct  TEXT
  theircurrency TEXT
  theiramount   TEXT
  timeout_days  INTEGER — default 14
  is_public     INTEGER — 0=private, 1=public (visible to all users)
  created_at    INTEGER
  updated_at    INTEGER
"""

import sqlite3
import os
import time
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(os.getenv("DB_PATH", "data/hf_dash.db"))

TEMPLATE_FIELDS = [
    "id", "uid", "name", "position", "terms",
    "yourproduct", "yourcurrency", "youramount",
    "theirproduct", "theircurrency", "theiramount",
    "address", "middleman_uid",
    "timeout_days", "is_public", "created_at", "updated_at",
]


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


@contextmanager
def _db():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_templates_db() -> None:
    with _db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS contract_templates (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                uid           TEXT    NOT NULL,
                name          TEXT    NOT NULL DEFAULT 'Untitled',
                position      TEXT    NOT NULL DEFAULT 'selling',
                terms         TEXT    NOT NULL DEFAULT '',
                yourproduct   TEXT    NOT NULL DEFAULT '',
                yourcurrency  TEXT    NOT NULL DEFAULT 'other',
                youramount    TEXT    NOT NULL DEFAULT '0',
                theirproduct  TEXT    NOT NULL DEFAULT '',
                theircurrency TEXT    NOT NULL DEFAULT 'other',
                theiramount   TEXT    NOT NULL DEFAULT '0',
                address       TEXT    NOT NULL DEFAULT '',
                middleman_uid TEXT    NOT NULL DEFAULT '',
                timeout_days  INTEGER NOT NULL DEFAULT 14,
                is_public     INTEGER NOT NULL DEFAULT 0,
                created_at    INTEGER NOT NULL DEFAULT 0,
                updated_at    INTEGER NOT NULL DEFAULT 0
            );
        """)
        # Migrate existing tables that lack the new columns
        existing = {row[1] for row in conn.execute("PRAGMA table_info(contract_templates)").fetchall()}
        if 'address' not in existing:
            conn.execute("ALTER TABLE contract_templates ADD COLUMN address TEXT NOT NULL DEFAULT ''")
        if 'middleman_uid' not in existing:
            conn.execute("ALTER TABLE contract_templates ADD COLUMN middleman_uid TEXT NOT NULL DEFAULT ''")


def _row_to_dict(row) -> dict:
    d = dict(row)
    d["is_public"] = bool(d["is_public"])
    return d


def list_templates(uid: str) -> list[dict]:
    """Return own templates + all public templates from others."""
    with _db() as conn:
        rows = conn.execute("""
            SELECT * FROM contract_templates
            WHERE uid = ? OR is_public = 1
            ORDER BY uid = ? DESC, updated_at DESC
        """, (uid, uid)).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_template(tid: int, uid: str) -> dict | None:
    """Get a single template — must be owned or public."""
    with _db() as conn:
        row = conn.execute("""
            SELECT * FROM contract_templates
            WHERE id = ? AND (uid = ? OR is_public = 1)
        """, (tid, uid)).fetchone()
    return _row_to_dict(row) if row else None


def create_template(uid: str, data: dict) -> int:
    now = int(time.time())
    with _db() as conn:
        cur = conn.execute("""
            INSERT INTO contract_templates
              (uid, name, position, terms, yourproduct, yourcurrency, youramount,
               theirproduct, theircurrency, theiramount,
               address, middleman_uid, timeout_days, is_public,
               created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            uid,
            data.get("name", "Untitled")[:100],
            data.get("position", "selling"),
            data.get("terms", ""),
            data.get("yourproduct", ""),
            data.get("yourcurrency", "other"),
            str(data.get("youramount", "0")),
            data.get("theirproduct", ""),
            data.get("theircurrency", "other"),
            str(data.get("theiramount", "0")),
            data.get("address", ""),
            data.get("middleman_uid", ""),
            int(data.get("timeout_days", 14)),
            int(bool(data.get("is_public", False))),
            now, now,
        ))
    return cur.lastrowid


def update_template(tid: int, uid: str, data: dict) -> bool:
    now = int(time.time())
    with _db() as conn:
        cur = conn.execute("""
            UPDATE contract_templates SET
              name=?, position=?, terms=?,
              yourproduct=?, yourcurrency=?, youramount=?,
              theirproduct=?, theircurrency=?, theiramount=?,
              address=?, middleman_uid=?,
              timeout_days=?, is_public=?, updated_at=?
            WHERE id = ? AND uid = ?
        """, (
            data.get("name", "Untitled")[:100],
            data.get("position", "selling"),
            data.get("terms", ""),
            data.get("yourproduct", ""),
            data.get("yourcurrency", "other"),
            str(data.get("youramount", "0")),
            data.get("theirproduct", ""),
            data.get("theircurrency", "other"),
            str(data.get("theiramount", "0")),
            data.get("address", ""),
            data.get("middleman_uid", ""),
            int(data.get("timeout_days", 14)),
            int(bool(data.get("is_public", False))),
            now, tid, uid,
        ))
    return cur.rowcount > 0


def delete_template(tid: int, uid: str) -> bool:
    with _db() as conn:
        cur = conn.execute(
            "DELETE FROM contract_templates WHERE id = ? AND uid = ?",
            (tid, uid)
        )
    return cur.rowcount > 0
