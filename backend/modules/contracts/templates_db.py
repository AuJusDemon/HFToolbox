"""
modules/contracts/templates_db.py — Contract template persistence.

Table: contract_templates
  id            INTEGER PRIMARY KEY
  uid           TEXT — owner
  name          TEXT — display name
  position      TEXT — selling/buying/exchanging/trading/vouchcopy
  terms         TEXT — full terms BBCode
  yourproduct   TEXT
  yourcurrency  TEXT
  youramount    TEXT
  theirproduct  TEXT
  theircurrency TEXT
  theiramount   TEXT
  address       TEXT
  middleman_uid TEXT
  timeout_days  INTEGER — default 14
  is_public     INTEGER — 0=private, 1=public
  created_at    INTEGER
  updated_at    INTEGER
"""

import sqlite3
import time
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path("data/hf_dash.db")

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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS contract_templates (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                uid           TEXT    NOT NULL,
                name          TEXT    NOT NULL DEFAULT 'Untitled',
                position      TEXT    NOT NULL DEFAULT 'selling',
                terms         TEXT    NOT NULL,
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
                created_at    INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                updated_at    INTEGER NOT NULL DEFAULT (strftime('%s','now'))
            )
        """)


def list_templates(uid: str) -> list[dict]:
    """Return all templates visible to this user (own + public)."""
    with _db() as conn:
        rows = conn.execute(
            """SELECT * FROM contract_templates
               WHERE uid=? OR is_public=1
               ORDER BY updated_at DESC""",
            (uid,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_template(template_id: int, uid: str) -> dict | None:
    """Get a single template if user is owner or it's public."""
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM contract_templates WHERE id=? AND (uid=? OR is_public=1)",
            (template_id, uid)
        ).fetchone()
        return dict(row) if row else None


def create_template(uid: str, data: dict) -> dict:
    now = int(time.time())
    with _db() as conn:
        cur = conn.execute("""
            INSERT INTO contract_templates
                (uid, name, position, terms, yourproduct, yourcurrency, youramount,
                 theirproduct, theircurrency, theiramount, address, middleman_uid,
                 timeout_days, is_public, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            uid,
            data.get("name", "Untitled"),
            data.get("position", "selling"),
            data.get("terms", ""),
            data.get("yourproduct", ""),
            data.get("yourcurrency", "other"),
            data.get("youramount", "0"),
            data.get("theirproduct", ""),
            data.get("theircurrency", "other"),
            data.get("theiramount", "0"),
            data.get("address", ""),
            data.get("middleman_uid", ""),
            int(data.get("timeout_days", 14)),
            int(bool(data.get("is_public", False))),
            now, now,
        ))
        new_id = cur.lastrowid
        row = conn.execute("SELECT * FROM contract_templates WHERE id=?", (new_id,)).fetchone()
        return dict(row)


def update_template(template_id: int, uid: str, data: dict) -> dict | None:
    """Update a template. Owner only. Returns updated template or None if not found/not owner."""
    now = int(time.time())
    with _db() as conn:
        row = conn.execute(
            "SELECT id FROM contract_templates WHERE id=? AND uid=?", (template_id, uid)
        ).fetchone()
        if not row:
            return None
        conn.execute("""
            UPDATE contract_templates SET
                name=?, position=?, terms=?,
                yourproduct=?, yourcurrency=?, youramount=?,
                theirproduct=?, theircurrency=?, theiramount=?,
                address=?, middleman_uid=?, timeout_days=?, is_public=?, updated_at=?
            WHERE id=? AND uid=?
        """, (
            data.get("name", "Untitled"),
            data.get("position", "selling"),
            data.get("terms", ""),
            data.get("yourproduct", ""),
            data.get("yourcurrency", "other"),
            data.get("youramount", "0"),
            data.get("theirproduct", ""),
            data.get("theircurrency", "other"),
            data.get("theiramount", "0"),
            data.get("address", ""),
            data.get("middleman_uid", ""),
            int(data.get("timeout_days", 14)),
            int(bool(data.get("is_public", False))),
            now,
            template_id, uid,
        ))
        updated = conn.execute("SELECT * FROM contract_templates WHERE id=?", (template_id,)).fetchone()
        return dict(updated)


def delete_template(template_id: int, uid: str) -> bool:
    """Delete a template. Owner only."""
    with _db() as conn:
        cur = conn.execute(
            "DELETE FROM contract_templates WHERE id=? AND uid=?", (template_id, uid)
        )
        return cur.rowcount > 0


def delete_user_templates(uid: str) -> None:
    with _db() as conn:
        conn.execute("DELETE FROM contract_templates WHERE uid=?", (uid,))
